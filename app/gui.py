from __future__ import annotations

import threading
import tkinter.messagebox as mbox
from datetime import date
from pathlib import Path

import customtkinter as ctk
from tkcalendar import DateEntry

from app.apilo_auth import authenticate, ApiloAuthError
from app.browser_session import open_login, has_session
from app.config import AppConfig, ConfigError, bootstrap_config, load_config, save_config, safe_config_preview
from app.logging_setup import setup_logging
from app.pipeline import DocumentPipeline


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Auto_Potwierdzenia")
        self.geometry("1020x780")

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
            return bootstrap_config(self.config_path)

    def _build_ui(self) -> None:
        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        # === Konfiguracja Apilo (OAuth) ===
        cfg_label = ctk.CTkLabel(frame, text="Konfiguracja Apilo (OAuth)", font=("Arial", 16, "bold"))
        cfg_label.pack(anchor="w", pady=(8, 4), padx=8)

        cred_frame = ctk.CTkFrame(frame)
        cred_frame.pack(fill="x", padx=8, pady=4)

        ctk.CTkLabel(cred_frame, text="Client ID:").grid(row=0, column=0, padx=4, pady=2, sticky="w")
        self.client_id_entry = ctk.CTkEntry(cred_frame, width=300, placeholder_text="Client ID z panelu Apilo")
        self.client_id_entry.grid(row=0, column=1, padx=4, pady=2)
        self.client_id_entry.insert(0, self.config_obj.apilo_client_id)

        ctk.CTkLabel(cred_frame, text="Client Secret:").grid(row=0, column=2, padx=4, pady=2, sticky="w")
        self.client_secret_entry = ctk.CTkEntry(cred_frame, width=300, placeholder_text="Client Secret", show="*")
        self.client_secret_entry.grid(row=0, column=3, padx=4, pady=2)
        self.client_secret_entry.insert(0, self.config_obj.apilo_client_secret)

        ctk.CTkLabel(cred_frame, text="Kod autoryzacji:").grid(row=1, column=0, padx=4, pady=2, sticky="w")
        self.auth_code_entry = ctk.CTkEntry(cred_frame, width=300, placeholder_text="Kod autoryzacji z panelu Apilo")
        self.auth_code_entry.grid(row=1, column=1, padx=4, pady=2)
        self.auth_code_entry.insert(0, self.config_obj.apilo_auth_code)

        btn_frame_cfg = ctk.CTkFrame(cred_frame, fg_color="transparent")
        btn_frame_cfg.grid(row=1, column=2, columnspan=2, padx=4, pady=2, sticky="w")

        self.connect_btn = ctk.CTkButton(btn_frame_cfg, text="Polacz z Apilo", command=self._connect_apilo,
                                          fg_color="#2196F3")
        self.connect_btn.pack(side="left", padx=4)

        save_btn = ctk.CTkButton(btn_frame_cfg, text="Zapisz dane", command=self._save_credentials,
                                  fg_color="#607D8B")
        save_btn.pack(side="left", padx=4)

        self.cfg_preview = ctk.CTkLabel(frame, text="", font=("Consolas", 10))
        self.cfg_preview.pack(anchor="w", padx=8, pady=(2, 8))

        # === Zakres dat ===
        date_label = ctk.CTkLabel(frame, text="Zakres dat", font=("Arial", 16, "bold"))
        date_label.pack(anchor="w", padx=8)

        date_frame = ctk.CTkFrame(frame, fg_color="transparent")
        date_frame.pack(fill="x", padx=8, pady=2)

        today = date.today()
        month_start = today.replace(day=1)

        ctk.CTkLabel(date_frame, text="Od:").pack(side="left", padx=4)
        self.from_cal = DateEntry(date_frame, width=14, date_pattern="yyyy-mm-dd",
                                   year=month_start.year, month=month_start.month, day=month_start.day,
                                   font=("Arial", 11))
        self.from_cal.pack(side="left", padx=4)

        ctk.CTkLabel(date_frame, text="Do:").pack(side="left", padx=(16, 4))
        self.to_cal = DateEntry(date_frame, width=14, date_pattern="yyyy-mm-dd",
                                 year=today.year, month=today.month, day=today.day,
                                 font=("Arial", 11))
        self.to_cal.pack(side="left", padx=4)

        # === Ręczny wybór zamówień ===
        select_label = ctk.CTkLabel(
            frame,
            text="Wybor zamowien (opcjonalnie, rozdziel przecinkiem)",
            font=("Arial", 14, "bold"),
        )
        select_label.pack(anchor="w", padx=8, pady=(10, 4))

        self.apilo_orders_entry = ctk.CTkEntry(
            frame, width=960,
            placeholder_text="Numery Apilo (order_number / order_id), np. 12345, 12346",
        )
        self.apilo_orders_entry.pack(anchor="w", padx=8, pady=2)

        self.amazon_orders_entry = ctk.CTkEntry(
            frame, width=960,
            placeholder_text="Numery Amazon, np. 302-1234567-1234567, 302-1111111-2222222",
        )
        self.amazon_orders_entry.pack(anchor="w", padx=8, pady=2)

        # === Opcje ===
        opt_frame = ctk.CTkFrame(frame, fg_color="transparent")
        opt_frame.pack(fill="x", padx=8, pady=6)

        self.headless_var = ctk.BooleanVar(value=self.config_obj.playwright_headless)
        ctk.CTkCheckBox(opt_frame, text="Headless (tracking)", variable=self.headless_var).pack(side="left", padx=8)

        self.amazon_var = ctk.BooleanVar(value=self.config_obj.capture_amazon)
        ctk.CTkCheckBox(opt_frame, text="Screenshoty Amazon (FBA poza UE)", variable=self.amazon_var).pack(side="left", padx=8)

        self.apilo_panel_var = ctk.BooleanVar(value=self.config_obj.capture_apilo_panel)
        ctk.CTkCheckBox(opt_frame, text="Screenshoty Apilo (brak trackingu)", variable=self.apilo_panel_var).pack(side="left", padx=8)

        self.invoices_var = ctk.BooleanVar(value=self.config_obj.download_pl_invoices)
        ctk.CTkCheckBox(opt_frame, text="Pobierz faktury PL", variable=self.invoices_var).pack(side="left", padx=8)

        # === Logowanie do serwisow (raz, recznie) ===
        login_frame = ctk.CTkFrame(frame, fg_color="transparent")
        login_frame.pack(fill="x", padx=8, pady=2)

        ctk.CTkButton(login_frame, text="Zaloguj do Amazon EU", command=lambda: self._open_login("amazon"),
                      fg_color="#FF9900", hover_color="#CC7A00", text_color="black").pack(side="left", padx=4)
        ctk.CTkButton(login_frame, text="Zaloguj do Amazon USA", command=lambda: self._open_login("amazon_us"),
                      fg_color="#FF9900", hover_color="#CC7A00", text_color="black").pack(side="left", padx=4)
        ctk.CTkButton(login_frame, text="Zaloguj do panelu Apilo", command=lambda: self._open_login("apilo"),
                      fg_color="#2196F3", hover_color="#1976D2").pack(side="left", padx=4)
        self.login_status = ctk.CTkLabel(login_frame, text="", font=("Consolas", 10))
        self.login_status.pack(side="left", padx=8)
        self._refresh_login_status()

        # === Akcje ===
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=8, pady=6)

        self.run_btn = ctk.CTkButton(btn_frame, text="Generuj PDF-y", command=lambda: self._run_pipeline(False),
                                      fg_color="#4CAF50", hover_color="#388E3C", height=36)
        self.run_btn.pack(side="left", padx=4)

        self.test_btn = ctk.CTkButton(btn_frame, text="Test na 5 zamowieniach",
                                       command=lambda: self._run_pipeline(True),
                                       fg_color="#FF9800", hover_color="#F57C00", height=36)
        self.test_btn.pack(side="left", padx=4)

        # === Progress ===
        self.progress = ctk.CTkProgressBar(frame, width=960)
        self.progress.set(0)
        self.progress.pack(padx=8, pady=(4, 2))

        self.progress_label = ctk.CTkLabel(frame, text="Postep: 0/0")
        self.progress_label.pack(anchor="w", padx=8)

        # === Logi ===
        log_label = ctk.CTkLabel(frame, text="Logi", font=("Arial", 14, "bold"))
        log_label.pack(anchor="w", padx=8, pady=(8, 2))

        self.log_box = ctk.CTkTextbox(frame, width=960, height=220, font=("Consolas", 10))
        self.log_box.pack(padx=8, pady=4, fill="both", expand=True)

    def _append_log(self, msg: str) -> None:
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.update_idletasks()

    def _refresh_login_status(self) -> None:
        a = "✓" if has_session(self.config_obj, "amazon") else "✗"
        p = "✓" if has_session(self.config_obj, "apilo") else "✗"
        self.login_status.configure(text=f"Sesje: Amazon {a}  Apilo {p}")

    def _open_login(self, site: str) -> None:
        if site == "apilo" and not self.config_obj.apilo_panel_url:
            mbox.showerror("Blad", "Najpierw ustaw adres panelu Apilo (apilo_panel_url) w config.json.")
            return
        self._append_log(f"Otwieram logowanie: {site}. Zaloguj sie i ZAMKNIJ okno przegladarki.")

        def runner() -> None:
            try:
                open_login(site, self.config_obj, log_cb=self._append_log)
            except Exception as exc:
                self._append_log(f"Logowanie {site} nie powiodlo sie: {exc}")
            finally:
                self._refresh_login_status()

        threading.Thread(target=runner, daemon=True).start()

    def _save_credentials(self) -> None:
        self.config_obj.apilo_client_id = self.client_id_entry.get().strip()
        self.config_obj.apilo_client_secret = self.client_secret_entry.get().strip()
        self.config_obj.apilo_auth_code = self.auth_code_entry.get().strip()
        save_config(self.config_obj, self.config_path)
        self._refresh_config_preview()
        mbox.showinfo("OK", "Dane zapisane do config.json.")

    def _connect_apilo(self) -> None:
        self._save_credentials()
        try:
            self.config_obj = authenticate(self.config_obj)
            self._refresh_config_preview()
            self._append_log("Polaczono z Apilo — token uzyskany pomyslnie.")
            mbox.showinfo("OK", "Polaczono z Apilo! Token wazny 21 dni.")
        except ApiloAuthError as exc:
            self._append_log(f"Blad polaczenia z Apilo: {exc}")
            mbox.showerror("Blad", str(exc))

    def _refresh_config_preview(self) -> None:
        self.cfg_preview.configure(text=safe_config_preview(self.config_obj))

    def _set_running(self, is_running: bool) -> None:
        state = "disabled" if is_running else "normal"
        self.run_btn.configure(state=state)
        self.test_btn.configure(state=state)
        self.connect_btn.configure(state=state)

    @staticmethod
    def _parse_csv_values(raw: str) -> set[str]:
        return {item.strip() for item in raw.split(",") if item.strip()}

    def _run_pipeline(self, test_mode: bool) -> None:
        try:
            self.config_obj = load_config(self.config_path)
        except ConfigError as exc:
            mbox.showerror("Blad konfiguracji", str(exc))
            return

        if not self.config_obj.apilo_access_token:
            mbox.showerror("Blad", "Najpierw kliknij 'Polacz z Apilo' zeby uzyskac token.")
            return

        d_from = self.from_cal.get_date()
        d_to = self.to_cal.get_date()

        self.config_obj.playwright_headless = self.headless_var.get()
        self.config_obj.capture_amazon = self.amazon_var.get()
        self.config_obj.capture_apilo_panel = self.apilo_panel_var.get()
        self.config_obj.download_pl_invoices = self.invoices_var.get()

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
                    self.progress_label.configure(text=f"Postep: {current}/{total}")
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
                    f"Gotowe. OK: {ok_count}, bledy: {err_count}. Katalog: {out.output_dir}"
                )
                mbox.showinfo("Zakonczone", f"Wyniki zapisane w: {out.output_dir}")
            except Exception as exc:
                self._append_log(f"Blad krytyczny: {exc}")
                mbox.showerror("Blad krytyczny", str(exc))
            finally:
                self._set_running(False)

        threading.Thread(target=runner, daemon=True).start()


def run_app() -> None:
    app = App()
    app.mainloop()
