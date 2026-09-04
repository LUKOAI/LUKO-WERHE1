"""Wysyłka arkuszy do Google Sheets (gspread + konto serwisowe).

Konfiguracja po stronie klienta:
  1. Google Cloud: projekt -> włączyć Google Sheets API i Google Drive API.
  2. Utworzyć konto serwisowe, pobrać klucz JSON.
  3. Udostępnić docelowy arkusz (Udostępnij -> e-mail konta serwisowego, Edytor).
  4. Uruchomić: --sheet-id <ID z URL> --credentials klucz.json
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from .excel import safe_sheet_name
from .merge import Formula, Sheet

log = logging.getLogger(__name__)


def to_sheet_values(rows: list[list[Any]]) -> list[list[Any]]:
    """Konwersja wartości na typy akceptowane przez Sheets API (USER_ENTERED)."""
    out: list[list[Any]] = []
    for row in rows:
        conv: list[Any] = []
        for v in row:
            if v is None:
                conv.append("")
            elif isinstance(v, Formula):
                conv.append(str(v))
            elif isinstance(v, date):
                conv.append(v.isoformat())
            elif isinstance(v, bool):
                conv.append("TAK" if v else "NIE")
            elif isinstance(v, (int, float)):
                conv.append(v)
            else:
                s = str(v)
                # tekst zaczynający się od '=' / '+' byłby zinterpretowany jako formuła
                conv.append("'" + s if s[:1] in "=+" else s)
        out.append(conv)
    return out


def extract_spreadsheet_id(value: str) -> str:
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", value or "")
    return m.group(1) if m else (value or "").strip()


def push_sheets(
    spreadsheet_id: str,
    sheets: list[Sheet],
    credentials_path: str | None = None,
    client=None,
    reorder: bool = True,
) -> list[str]:
    """Zapisuje każdą tabelę jako zakładkę (istniejąca o tej nazwie jest czyszczona).

    `client` – opcjonalnie gotowy klient gspread (do testów).
    Zwraca listę nazw zapisanych zakładek.
    """
    if client is None:
        import gspread  # import lokalny

        if not credentials_path:
            raise ValueError("podaj ścieżkę do klucza konta serwisowego (--credentials)")
        client = gspread.service_account(filename=credentials_path)
    sh = client.open_by_key(extract_spreadsheet_id(spreadsheet_id))
    existing = {ws.title: ws for ws in sh.worksheets()}
    used: set[str] = set()
    written: list[str] = []
    ordered = []
    for sheet in sheets:
        name = safe_sheet_name(sheet.name, used) if sheet.name not in existing else sheet.name
        values = to_sheet_values(sheet.rows)
        nrows = max(len(values) + 5, 20)
        ncols = max((len(r) for r in values), default=1) + 2
        ws = existing.get(name)
        if ws is None:
            ws = sh.add_worksheet(title=name, rows=nrows, cols=ncols)
            existing[name] = ws
        else:
            ws.clear()
            try:
                ws.resize(rows=nrows, cols=ncols)
            except Exception as exc:  # noqa: BLE001 – resize nie jest krytyczny
                log.debug("resize %s: %s", name, exc)
        ws.update(values=values, range_name="A1", value_input_option="USER_ENTERED")
        try:
            ws.format(f"{sheet.header_row}:{sheet.header_row}", {"textFormat": {"bold": True}})
            ws.freeze(rows=sheet.header_row, cols=1)
            if sheet.money_cols and len(values) > sheet.header_row:
                from gspread.utils import rowcol_to_a1

                ranges = [
                    f"{rowcol_to_a1(sheet.header_row + 1, c)}:{rowcol_to_a1(len(values), c)}"
                    for c in sheet.money_cols
                ]
                ws.batch_format([{"range": rg, "format": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}}} for rg in ranges])
        except Exception as exc:  # noqa: BLE001 – formatowanie nie jest krytyczne
            log.warning("formatowanie zakładki %s nie powiodło się: %s", name, exc)
        written.append(name)
        ordered.append(ws)
        log.info("Google Sheets: zakładka %s – %d wierszy", name, len(values))
    if reorder and ordered:
        try:
            rest = [ws for ws in sh.worksheets() if ws.title not in written]
            sh.reorder_worksheets(ordered + rest)
        except Exception as exc:  # noqa: BLE001
            log.debug("reorder: %s", exc)
    return written
