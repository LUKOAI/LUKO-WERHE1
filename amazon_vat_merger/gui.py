"""LUKO AmaFakt – okienko (tkinter, biblioteka standardowa) dla osoby, która nie używa terminala.

Uruchomienie: python -m amazon_vat_merger.gui  (albo zbudowany LUKO-AmaFakt.exe).
Ustawienia (ścieżki, ID arkusza) są zapamiętywane w pliku konfiguracyjnym użytkownika.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from . import APP_NAME, APP_SLUG, AUTHOR, COPYRIGHT_YEAR, SUPPORT_EMAIL, __version__
from .job import run_job

APP_TITLE = f"{APP_NAME} — faktury Amazon do arkusza"
LOG_NAME = "luko-amafakt.log"          # dziennik techniczny w folderze wyników (do wysłania przy problemach)
OLD_APP_SLUGS = ("AmazonVAT",)         # wcześniejsza nazwa programu – ustawienia są przenoszone


def config_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home() / ".config")
    return base / APP_SLUG / "config.json"


def load_config() -> dict:
    """Ustawienia z bieżącej lokalizacji; jeśli ich nie ma – z folderu starej nazwy programu (i przeniesienie)."""
    current = config_path()
    candidates = [current] + [current.parent.parent / old / "config.json" for old in OLD_APP_SLUGS]
    for path in candidates:
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(cfg, dict):
            continue
        if path != current:
            save_config(cfg)
        return cfg
    return {}


def save_config(cfg: dict) -> None:
    try:
        config_path().parent.mkdir(parents=True, exist_ok=True)
        config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def open_path(path: "Path | str") -> None:
    """Otwiera plik/folder w systemie; działa też dla adresów (mailto:, https://)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:  # noqa: BLE001
        pass


class _QueueHandler(logging.Handler):
    def __init__(self, q: "queue.Queue[str]") -> None:
        super().__init__()
        self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(self.format(record))


def main() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter import font as tkfont

    cfg = load_config()
    root = tk.Tk()
    root.title(f"{APP_TITLE}  (v{__version__})")
    try:  # ikona: obok pliku exe (PyInstaller rozpakowuje do sys._MEIPASS) albo w repo (assets/)
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        ico, png = base / "assets" / "icon.ico", base / "assets" / "icon.png"
        if sys.platform.startswith("win") and ico.exists():
            root.iconbitmap(default=str(ico))      # .ico z klatkami BMP – także dla okien dialogowych
        elif png.exists():
            root.iconphoto(True, tk.PhotoImage(file=str(png)))
    except Exception:  # noqa: BLE001
        pass
    root.geometry("860x640")
    root.minsize(760, 560)

    vars_ = {
        "csv": tk.StringVar(value=cfg.get("csv", "")),
        "pdf": tk.StringVar(value=cfg.get("pdf", "")),
        "rates": tk.StringVar(value=cfg.get("rates", "")),
        "out": tk.StringVar(value=cfg.get("out", str(Path.home() / APP_SLUG / "wyniki"))),
        "sheet": tk.StringVar(value=cfg.get("sheet", "")),
        "cred": tk.StringVar(value=cfg.get("cred", "")),
    }
    use_nbp = tk.BooleanVar(value=cfg.get("use_nbp", True))
    log_q: "queue.Queue[str]" = queue.Queue()
    state = {"running": False, "last_out": None}

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)
    frm.columnconfigure(1, weight=1)

    def row(r: int, label: str, var: tk.StringVar, browse) -> None:
        ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=var).grid(row=r, column=1, sticky="ew", padx=6)
        if browse:
            ttk.Button(frm, text="Wybierz…", command=browse).grid(row=r, column=2)

    def pick_csv():
        files = filedialog.askopenfilenames(title="Raport(y) CSV z Seller Central", filetypes=[("CSV", "*.csv"), ("Wszystkie", "*.*")])
        if files:
            vars_["csv"].set(";".join(files))

    def pick_dir(var: tk.StringVar, title: str):
        def _f():
            d = filedialog.askdirectory(title=title)
            if d:
                var.set(d)
        return _f

    def pick_file(var: tk.StringVar, title: str, types):
        def _f():
            f = filedialog.askopenfilename(title=title, filetypes=types)
            if f:
                var.set(f)
        return _f

    row(0, "Raport CSV (Amazon VAT Transactions):", vars_["csv"], pick_csv)
    row(1, "Folder z fakturami PDF:", vars_["pdf"], pick_dir(vars_["pdf"], "Folder z fakturami PDF"))
    row(2, "Folder na wyniki:", vars_["out"], pick_dir(vars_["out"], "Folder na wyniki"))
    row(3, "Plik kursów (opcjonalnie):", vars_["rates"], pick_file(vars_["rates"], "Plik kursów CSV", [("CSV", "*.csv")]))
    row(4, "ID arkusza Google (opcjonalnie):", vars_["sheet"], None)
    row(5, "Klucz konta serwisowego JSON (opcjonalnie):", vars_["cred"], pick_file(vars_["cred"], "Klucz konta serwisowego", [("JSON", "*.json")]))
    ttk.Checkbutton(frm, text="Pobieraj kursy z API NBP (tabela A)", variable=use_nbp).grid(row=6, column=1, sticky="w", pady=3)

    btns = ttk.Frame(frm)
    btns.grid(row=7, column=0, columnspan=3, sticky="ew", pady=8)
    run_btn = ttk.Button(btns, text="Uruchom")
    run_btn.pack(side="left")
    open_btn = ttk.Button(btns, text="Otwórz wynik", state="disabled")
    open_btn.pack(side="left", padx=6)
    ttk.Button(btns, text="Otwórz folder wyników", command=lambda: open_path(Path(vars_["out"].get()))).pack(side="left")
    status = ttk.Label(btns, text="")
    status.pack(side="left", padx=12)

    log_box = tk.Text(frm, height=18, wrap="word", state="disabled")
    log_box.grid(row=8, column=0, columnspan=3, sticky="nsew")
    frm.rowconfigure(8, weight=1)
    sb = ttk.Scrollbar(frm, command=log_box.yview)
    sb.grid(row=8, column=3, sticky="ns")
    log_box.configure(yscrollcommand=sb.set)

    # stopka: autor, wersja, kontakt do pomocy (adres klikalny – otwiera program pocztowy)
    foot = ttk.Frame(frm)
    foot.grid(row=9, column=0, columnspan=4, sticky="ew", pady=(6, 0))
    ttk.Label(foot, text=f"{APP_NAME} v{__version__}  ·  © {COPYRIGHT_YEAR} {AUTHOR}  ·  pomoc i awarie: ",
              foreground="#666666").pack(side="left")
    link_font = tkfont.nametofont("TkDefaultFont").copy()   # ta sama czcionka co reszta stopki, z podkreśleniem
    link_font.configure(underline=True)
    mail = ttk.Label(foot, text=SUPPORT_EMAIL, foreground="#0563C1", cursor="hand2", font=link_font)
    mail.pack(side="left")
    mail.link_font = link_font  # referencja, żeby obiekt czcionki nie został zwolniony
    mail.bind("<Button-1>", lambda _e: open_path(f"mailto:{SUPPORT_EMAIL}?subject={quote(f'{APP_NAME} v{__version__}')}"))

    def append_log(text: str) -> None:
        log_box.configure(state="normal")
        log_box.insert("end", text + "\n")
        log_box.see("end")
        log_box.configure(state="disabled")

    def poll_log() -> None:
        try:
            while True:
                append_log(log_q.get_nowait())
        except queue.Empty:
            pass
        root.after(200, poll_log)

    def current_cfg() -> dict:
        return {k: v.get() for k, v in vars_.items()} | {"use_nbp": use_nbp.get()}

    def worker(params: dict) -> None:
        handler = _QueueHandler(log_q)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        handler.setLevel(logging.INFO)
        logger = logging.getLogger("amazon_vat_merger")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        out_dir = Path(params["out"]) if params["out"] else Path.home() / APP_SLUG / "wyniki"
        file_handler: logging.Handler | None = None
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            # pełny dziennik (ze szczegółami technicznymi) do pliku w folderze wyników
            file_handler = logging.FileHandler(out_dir / LOG_NAME, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)
            logger.info("%s v%s – start", APP_NAME, __version__)
            csvs = [p for p in params["csv"].split(";") if p.strip()]
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = out_dir / f"amazon_vat_{stamp}.xlsx"
            job = run_job(
                csv_paths=csvs, pdf_sources=[params["pdf"]] if params["pdf"] else [], out_path=out,
                rates_file=params["rates"] or None, use_nbp=params["use_nbp"],
                sheet_id=params["sheet"].strip() or None, credentials=params["cred"] or None,
                json_dump=out_dir / "faktury.json",
            )
            log_q.put("GOTOWE: " + job.summary)
            log_q.put(f"Plik: {job.xlsx_path}")
            diag = [s for s in job.result.rows if s.invoice is None]
            if diag:
                log_q.put(f"Brak PDF dla {len(diag)} transakcji – lista w zakładce Diagnostyka.")
            state["last_out"] = job.xlsx_path
            if job.push_error:
                log_q.put("UWAGA: arkusz Google NIE został zaktualizowany (powód wyżej). "
                          "Plik Excel jest gotowy – przycisk „Otwórz wynik”.")
                final = "Zakończono – błąd Google Sheets"
            else:
                final = "Zakończono"
            root.after(0, lambda: (open_btn.configure(state="normal"), status.configure(text=final)))
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).strip() or type(exc).__name__
            if not isinstance(exc, (ValueError, PermissionError, RuntimeError)):
                msg = f"{type(exc).__name__}: {msg}"
            log_q.put(f"BŁĄD: {msg}")
            logger.debug("szczegóły błędu", exc_info=True)   # tylko do pliku dziennika
            if file_handler is not None:
                log_q.put(f"Szczegóły techniczne: {out_dir / LOG_NAME} (ten plik można wysłać do pomocy).")
            root.after(0, lambda: status.configure(text="Błąd – patrz dziennik"))
        finally:
            logger.removeHandler(handler)
            if file_handler is not None:
                logger.removeHandler(file_handler)
                file_handler.close()
            state["running"] = False
            root.after(0, lambda: run_btn.configure(state="normal"))

    def on_run() -> None:
        if state["running"]:
            return
        params = current_cfg()
        if not params["csv"]:
            messagebox.showwarning(APP_TITLE, "Wskaż raport CSV z Seller Central.")
            return
        if not params["pdf"]:
            if not messagebox.askyesno(APP_TITLE, "Nie wskazano folderu z fakturami PDF. Zbudować arkusz tylko z raportu CSV?"):
                return
        if params["sheet"] and not params["cred"]:
            messagebox.showwarning(APP_TITLE, "Podano ID arkusza Google, ale nie wskazano klucza konta serwisowego (JSON).")
            return
        save_config(params)
        state["running"] = True
        run_btn.configure(state="disabled")
        open_btn.configure(state="disabled")
        status.configure(text="Przetwarzam…")
        append_log(f"--- start {datetime.now():%Y-%m-%d %H:%M:%S} ---")
        threading.Thread(target=worker, args=(params,), daemon=True).start()

    run_btn.configure(command=on_run)
    open_btn.configure(command=lambda: state["last_out"] and open_path(state["last_out"]))
    def on_close() -> None:
        if state["running"] and not messagebox.askyesno(
            APP_TITLE,
            "Przetwarzanie jeszcze trwa. Zamknąć mimo to?\n\n"
            "Plik wynikowy może być niekompletny, a arkusz Google zaktualizowany tylko częściowo.",
        ):
            return
        save_config(current_cfg())
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    poll_log()
    root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
