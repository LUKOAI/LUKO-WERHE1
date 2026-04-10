from __future__ import annotations

import threading
import tkinter.messagebox as mbox
from datetime import date
from pathlib import Path

import customtkinter as ctk

from app.config import AppConfig, ConfigError, bootstrap_config, load_config, save_config, safe_config_preview
from app.logging_setup import setup_logging
from app.pipeline import DocumentPipeline


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("WERHE/WERKON - Generator PDF dla urzędu")
        self.geometry("980x700")

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.config_path = Path("config.json")
        self.config_obj = self._load_or_bootstrap()
        self.logger = setup_logging(Path("logs/app.log"), self._append_log)

        self._build_ui()
        self._refresh_config_preview()

    def _load_or_bootstrap(self) -> AppConfig:
        try:
            return load_config(self.config_path)
        except ConfigError:
            cfg = bootstrap_config(self.config_path)
            return cfg

    def _build_ui(self) -> None:
        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        # Konfiguracja
        cfg_label = ctk.CTkLabel(frame, text="Konfiguracja Apilo", font=("Arial", 16, "bold"))
        cfg_label.pack(anchor="w", pady=(8, 4), padx=8)

        self.token_entry = ctk.CTkEntry(frame, width=520, placeholder_text="Bearer token Apilo")
        self.token_entry.insert(0, self.config_obj.apilo_token)
        self.token_entry.pack(anchor="w", padx=8)

        save_btn = ctk.CTkButton(frame, text="Zapisz token", command=self._save_token)
        save_btn.pack(anchor="w", padx=8, pady=(6, 10))

        self.cfg_preview = ctk.CTkLabel(frame, text="")
        self.cfg_preview.pack(anchor="w", padx=8, pady=(0, 10))

        # Zakres dat
        date_label = ctk.CTkLabel(frame, text="Zakres dat (YYYY-MM-DD)", font=("Arial", 16, "bold"))
        date_label.pack(anchor="w", padx=8)

        today = date.today()
        month_start = today.replace(day=1)

        self.from_entry = ctk.CTkEntry(frame, width=180)
        self.from_entry.insert(0, month_start.isoformat())
        self.from_entry.pack(anchor="w", padx=8, pady=2)

        self.to_entry = ctk.CTkEntry(frame, width=180)
        self.to_entry.insert(0, today.isoformat())
        self.to_entry.pack(anchor="w", padx=8, pady=2)

        # Ręczny wybór zamówień
        select_label = ctk.CTkLabel(
            frame,
            text="Wybór zamówień (opcjonalnie, wartości rozdziel przecinkiem)",
            font=("Arial", 14, "bold"),
        )
        select_label.pack(anchor="w", padx=8, pady=(12, 4))

        self.apilo_orders_entry = ctk.CTkEntry(
            frame,
            width=940,
            placeholder_text="Numery Apilo (order_number / order_id), np. 12345, 12346",
        )
        self.apilo_orders_entry.pack(anchor="w", padx=8, pady=2)

        self.amazon_orders_entry = ctk.CTkEntry(
            frame,
            width=940,
            placeholder_text="Numery Amazon, np. 302-1234567-1234567, 302-1111111-2222222",
        )
        self.amazon_orders_entry.pack(anchor="w", padx=8, pady=2)

        # Akcje
        btn_frame = ctk.CTkFrame(frame)
        btn_frame.pack(fill="x", padx=8, pady=10)

        self.run_btn = ctk.CTkButton(btn_frame, text="Generuj PDF-y", command=lambda: self._run_pipeline(False))
        self.run_btn.pack(side="left", padx=4)

        self.test_btn = ctk.CTkButton(btn_frame, text="Test na 5 zamówieniach", command=lambda: self._run_pipeline(True))
        self.test_btn.pack(side="left", padx=4)

        # Progress
        self.progress = ctk.CTkProgressBar(frame, width=900)
        self.progress.set(0)
        self.progress.pack(padx=8, pady=(0, 8))

        self.progress_label = ctk.CTkLabel(frame, text="Postęp: 0/0")
        self.progress_label.pack(anchor="w", padx=8)

        # Logi
        log_label = ctk.CTkLabel(frame, text="Logi", font=("Arial", 14, "bold"))
        log_label.pack(anchor="w", padx=8, pady=(12, 4))

        self.log_box = ctk.CTkTextbox(frame, width=940, height=320)
        self.log_box.pack(padx=8, pady=4, fill="both", expand=True)

    def _append_log(self, msg: str) -> None:
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.update_idletasks()

    def _save_token(self) -> None:
        token = self.token_entry.get().strip()
        if not token:
            mbox.showerror("Błąd", "Token nie może być pusty.")
            return

        self.config_obj.apilo_token = token
        save_config(self.config_obj, self.config_path)
        self._refresh_config_preview()
        mbox.showinfo("OK", "Token zapisany.")

    def _refresh_config_preview(self) -> None:
        self.cfg_preview.configure(text=safe_config_preview(self.config_obj))

    def _set_running(self, is_running: bool) -> None:
        state = "disabled" if is_running else "normal"
        self.run_btn.configure(state=state)
        self.test_btn.configure(state=state)

    @staticmethod
    def _parse_csv_values(raw: str) -> set[str]:
        return {item.strip() for item in raw.split(",") if item.strip()}

    def _run_pipeline(self, test_mode: bool) -> None:
        try:
            self.config_obj = load_config(self.config_path)
        except ConfigError as exc:
            mbox.showerror("Błąd konfiguracji", str(exc))
            return

        try:
            d_from = date.fromisoformat(self.from_entry.get().strip())
            d_to = date.fromisoformat(self.to_entry.get().strip())
        except ValueError:
            mbox.showerror("Błąd", "Data musi mieć format YYYY-MM-DD")
            return

        self._set_running(True)
        self.progress.set(0)
        selected_apilo_numbers = self._parse_csv_values(self.apilo_orders_entry.get())
        selected_amazon_numbers = self._parse_csv_values(self.amazon_orders_entry.get())

        def runner() -> None:
            try:
                pipeline = DocumentPipeline(self.config_obj, self.logger)

                def on_progress(current: int, total: int) -> None:
                    pct = (current / total) if total else 0
                    self.progress.set(pct)
                    self.progress_label.configure(text=f"Postęp: {current}/{total}")
                    self.update_idletasks()

                out = pipeline.run(
                    date_from=d_from,
                    date_to=d_to,
                    test_mode=test_mode,
                    selected_apilo_numbers=selected_apilo_numbers,
                    selected_amazon_numbers=selected_amazon_numbers,
                    progress_cb=on_progress,
                    log_cb=self._append_log,
                )
                ok_count = len([r for r in out.processed if r.status == "ok"])
                err_count = len([r for r in out.processed if r.status == "error"])
                self._append_log(
                    f"Gotowe. OK: {ok_count}, błędy: {err_count}. Katalog: {out.output_dir}"
                )
                mbox.showinfo("Zakończono", f"Wyniki zapisane w: {out.output_dir}")
            except Exception as exc:  # noqa: BLE001
                self._append_log(f"Błąd krytyczny: {exc}")
                mbox.showerror("Błąd krytyczny", str(exc))
            finally:
                self._set_running(False)

        threading.Thread(target=runner, daemon=True).start()


def run_app() -> None:
    app = App()
    app.mainloop()
