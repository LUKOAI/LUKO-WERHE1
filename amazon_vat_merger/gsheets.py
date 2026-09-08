"""Wysyłka arkuszy do Google Sheets (gspread + konto serwisowe).

Konfiguracja po stronie klienta:
  1. Google Cloud: projekt -> włączyć Google Sheets API i Google Drive API.
  2. Utworzyć konto serwisowe, pobrać klucz JSON.
  3. Udostępnić docelowy arkusz (Udostępnij -> e-mail konta serwisowego, Edytor).
  4. Uruchomić: --sheet-id <ID z URL> --credentials klucz.json

Limity API (60 zapisów/min/użytkownik): na zakładkę idą 2-3 wywołania (clear, update,
ewentualnie resize), a formuły RAZEM i całe formatowanie jadą jednym batch_update; klient
gspread ma włączony backoff na HTTP 429. Wartości idą w trybie RAW: tekst zostaje tekstem
(bez prefiksu apostrofu), daty jako numery seryjne z formatem DATE.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from .excel import safe_sheet_name
from .merge import Formula, Sheet

log = logging.getLogger(__name__)


SHEETS_EPOCH = date(1899, 12, 30)


def to_sheet_values(rows: list[list[Any]]) -> list[list[Any]]:
    """Konwersja wartości pod zapis w trybie RAW (bez interpretacji przez Sheets).

    * tekst -> tekst 1:1 (bez prefiksu apostrofu; kody pocztowe, numery zamówień i SKU zostają
      tekstem, bo RAW nic nie parsuje),
    * liczby -> liczby,
    * daty -> numer seryjny arkusza (dni od 30.12.1899); kolumny dat dostają format DATE,
    * formuły -> pusta komórka tutaj, wpisywane osobno przez batchUpdate (patrz formula_cells).
    """
    out: list[list[Any]] = []
    for row in rows:
        conv: list[Any] = []
        for v in row:
            if v is None or isinstance(v, Formula):
                conv.append("")
            elif isinstance(v, date):
                conv.append((v - SHEETS_EPOCH).days)
            elif isinstance(v, bool):
                conv.append("TAK" if v else "NIE")
            elif isinstance(v, (int, float)):
                conv.append(v)
            else:
                conv.append(str(v))
        out.append(conv)
    return out


def formula_cells(rows: list[list[Any]]) -> list[tuple[int, int, str]]:
    """(wiersz 0-based, kolumna 0-based, formuła) dla komórek typu Formula."""
    return [(ri, ci, str(v)) for ri, row in enumerate(rows) for ci, v in enumerate(row) if isinstance(v, Formula)]


def extract_spreadsheet_id(value: str) -> str:
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", value or "")
    return m.group(1) if m else (value or "").strip()


def _formula_requests(sheet_id: int, sheet: Sheet) -> list[dict]:
    reqs: list[dict] = []
    for ri, ci, formula in formula_cells(sheet.rows):
        reqs.append({"updateCells": {
            "rows": [{"values": [{"userEnteredValue": {"formulaValue": formula}}]}],
            "fields": "userEnteredValue",
            "start": {"sheetId": sheet_id, "rowIndex": ri, "columnIndex": ci}}})
    return reqs


def _format_requests(sheet_id: int, sheet: Sheet, nrows: int, reset: bool) -> list[dict]:
    reqs: list[dict] = []
    if reset:
        reqs.append({"repeatCell": {"range": {"sheetId": sheet_id}, "cell": {"userEnteredFormat": {}},
                                    "fields": "userEnteredFormat"}})
    reqs.append({"updateSheetProperties": {
        "properties": {"sheetId": sheet_id,
                       "gridProperties": {"frozenRowCount": sheet.header_row, "frozenColumnCount": 1}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}})
    reqs.append({"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": sheet.header_row - 1, "endRowIndex": sheet.header_row},
        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
        "fields": "userEnteredFormat.textFormat.bold"}})
    if nrows > sheet.header_row:
        for c in sheet.money_cols:
            reqs.append({"repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": sheet.header_row, "endRowIndex": nrows,
                          "startColumnIndex": c - 1, "endColumnIndex": c},
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}}},
                "fields": "userEnteredFormat.numberFormat"}})
        for c in sheet.pct_cols:
            reqs.append({"repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": sheet.header_row, "endRowIndex": nrows,
                          "startColumnIndex": c - 1, "endColumnIndex": c},
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT", "pattern": "0%"}}},
                "fields": "userEnteredFormat.numberFormat"}})
        for c in sheet.date_cols:
            reqs.append({"repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": sheet.header_row, "endRowIndex": nrows,
                          "startColumnIndex": c - 1, "endColumnIndex": c},
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
                "fields": "userEnteredFormat.numberFormat"}})
    return reqs


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
        client = gspread.service_account(filename=credentials_path, http_client=gspread.BackOffHTTPClient)
    sh = client.open_by_key(extract_spreadsheet_id(spreadsheet_id))
    # Google Sheets nie rozróżnia wielkości liter w nazwach zakładek ("DE oss" == "DE OSS")
    existing = {ws.title.casefold(): ws for ws in sh.worksheets()}
    used: set[str] = set()
    written: list[str] = []
    ordered = []
    requests: list[dict] = []
    for sheet in sheets:
        ws = existing.get(sheet.name.casefold())
        name = ws.title if ws is not None else safe_sheet_name(sheet.name, used)
        values = to_sheet_values(sheet.rows)
        nrows = max(len(values) + 5, 20)
        ncols = max((len(r) for r in values), default=1) + 2
        reset = ws is not None
        if ws is None:
            ws = sh.add_worksheet(title=name, rows=nrows, cols=ncols)
            existing[name.casefold()] = ws
        else:
            ws.clear()
            if getattr(ws, "row_count", nrows) < nrows or getattr(ws, "col_count", ncols) < ncols:
                ws.resize(rows=max(nrows, getattr(ws, "row_count", 0)), cols=max(ncols, getattr(ws, "col_count", 0)))
        ws.update(values=values, range_name="A1", value_input_option="RAW")
        requests += _formula_requests(ws.id, sheet)
        requests += _format_requests(ws.id, sheet, len(values), reset)
        written.append(name)
        ordered.append(ws)
        log.info("Google Sheets: zakładka %s – %d wierszy", name, len(values))
    if requests:
        try:
            sh.batch_update({"requests": requests})
        except Exception as exc:  # noqa: BLE001 – formatowanie nie jest krytyczne
            log.warning("formatowanie zakładek nie powiodło się: %s", exc)
    if reorder and ordered:
        try:
            rest = [ws for ws in sh.worksheets() if ws.title not in written]
            sh.reorder_worksheets(ordered + rest)
        except Exception as exc:  # noqa: BLE001
            log.debug("reorder: %s", exc)
    return written
