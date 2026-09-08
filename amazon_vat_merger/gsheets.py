"""Wysyłka arkuszy do Google Sheets (gspread + konto serwisowe).

Konfiguracja po stronie klienta:
  1. Google Cloud: projekt -> włączyć Google Sheets API i Google Drive API.
  2. Utworzyć konto serwisowe, pobrać klucz JSON.
  3. Udostępnić docelowy arkusz (Udostępnij -> e-mail konta serwisowego, Edytor).
  4. Uruchomić: --sheet-id <ID z URL> --credentials klucz.json

Limity API (60 zapisów/min/użytkownik): na zakładkę idą 2-3 wywołania (clear, update,
ewentualnie resize). Formuły (wiersze RAZEM i linki w kolumnie „Zakładka” arkusza „Wszystko”)
jadą jednym batch_update – to zapis krytyczny: jego błąd przerywa wysyłkę z komunikatem. Całe
formatowanie jedzie drugim batch_update – niekrytycznym
(tylko ostrzeżenie). Klient gspread ma włączony backoff na HTTP 429. Wartości idą w trybie RAW:
tekst zostaje tekstem (bez prefiksu apostrofu), daty jako numery seryjne z formatem DATE.

Zakładki, które to narzędzie utworzyło w poprzednim uruchomieniu, a których teraz nie ma
(np. "DE OSS KOREKTA" bez korekt w tym miesiącu), są czyszczone i dostają notatkę – żeby
stare dane nie udawały aktualnych. Zakładki o innych nazwach nie są ruszane.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import APP_NAME
from .excel import safe_sheet_name
from .merge import Formula, Link, Sheet

log = logging.getLogger(__name__)


SHEETS_EPOCH = date(1899, 12, 30)

# zakładki tworzone przez to narzędzie: "DE OSS", "FR Lokalna KOREKTA", "XX B2B" ...
OWN_TAB_RE = re.compile(r"^[A-Z]{2} (OSS|Lokalna|WDT|B2B|Marketplace|Eksport)( KOREKTA)?$", re.IGNORECASE)
STALE_NOTE = ("Brak transakcji tego typu w ostatnim uruchomieniu – zakładka z poprzedniego okresu, "
              "wyczyszczona przez {app} {when}")


class GoogleSheetsError(RuntimeError):
    """Błąd zapisu do Google Sheets z komunikatem zrozumiałym dla osoby w biurze."""


@dataclass
class PushResult:
    written: list[str] = field(default_factory=list)          # zapisane zakładki (w kolejności)
    cleared_stale: list[str] = field(default_factory=list)    # wyczyszczone nieaktualne zakładki
    formatting_error: str | None = None                       # formatowanie nie weszło (dane i sumy tak)


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
            elif isinstance(v, datetime):
                conv.append((v.date() - SHEETS_EPOCH).days)
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


def formula_cells(rows: list[list[Any]]) -> list[tuple[int, int, Formula]]:
    """(wiersz 0-based, kolumna 0-based, formuła) dla komórek typu Formula (w tym Link)."""
    return [(ri, ci, v) for ri, row in enumerate(rows) for ci, v in enumerate(row) if isinstance(v, Formula)]


def extract_spreadsheet_id(value: str) -> str:
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", value or "")
    return m.group(1) if m else (value or "").strip()


def _formula_requests(sheet_id: int, sheet: Sheet, tabs: dict[str, tuple[int, str]] | None = None) -> list[dict]:
    """updateCells dla komórek-formuł; kolejne wiersze tej samej kolumny idą jednym żądaniem
    (kolumna „Zakładka” w „Wszystko” to jeden link na wiersz – bez grupowania byłyby tysiące żądań).

    `tabs` – nazwa zakładki (casefold) -> (sheetId, faktyczny tytuł), do linków HYPERLINK(#gid=…).
    Link do zakładki, której nie ma, zostaje zwykłym tekstem.
    """
    tabs = tabs or {}
    cells: list[tuple[int, int, dict]] = []
    for ri, ci, v in formula_cells(sheet.rows):
        if isinstance(v, Link):
            target = tabs.get(v.tab.casefold())
            value = {"formulaValue": v.gsheets_formula(*target)} if target is not None else {"stringValue": v.text}
        else:
            value = {"formulaValue": str(v)}
        cells.append((ci, ri, value))
    cells.sort(key=lambda c: (c[0], c[1]))
    reqs: list[dict] = []
    run: list[tuple[int, int, dict]] = []

    def flush() -> None:
        if run:
            reqs.append({"updateCells": {
                "rows": [{"values": [{"userEnteredValue": value}]} for _, _, value in run],
                "fields": "userEnteredValue",
                "start": {"sheetId": sheet_id, "rowIndex": run[0][1], "columnIndex": run[0][0]}}})
            run.clear()

    for cell in cells:
        if run and (cell[0] != run[-1][0] or cell[1] != run[-1][1] + 1):
            flush()
        run.append(cell)
    flush()
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
            # "0.0%" – stawki obniżone (5,5 %, 13,5 %, 2,1 %) muszą być widoczne, "0%" zaokrąglałoby je
            reqs.append({"repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": sheet.header_row, "endRowIndex": nrows,
                          "startColumnIndex": c - 1, "endColumnIndex": c},
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}}},
                "fields": "userEnteredFormat.numberFormat"}})
        for c in sheet.date_cols:
            reqs.append({"repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": sheet.header_row, "endRowIndex": nrows,
                          "startColumnIndex": c - 1, "endColumnIndex": c},
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
                "fields": "userEnteredFormat.numberFormat"}})
    return reqs


def _service_account_email(credentials_path: str | None) -> str:
    try:
        return str(json.loads(Path(credentials_path or "").read_text(encoding="utf-8")).get("client_email", ""))
    except Exception:  # noqa: BLE001
        return ""


def _no_access_message(key: str, credentials_path: str | None) -> str:
    email = _service_account_email(credentials_path) or "konta serwisowego (pole client_email w pliku klucza)"
    return (f"brak dostępu do arkusza {key} – udostępnij arkusz adresowi {email} jako Edytor "
            f"(Udostępnij → wpisz adres → Edytor)")


def _http_status(exc: BaseException) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code > 0:
        return code
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None)
    return status if isinstance(status, int) else None


def _open_spreadsheet(client, spreadsheet_id: str, credentials_path: str | None):
    key = extract_spreadsheet_id(spreadsheet_id)
    try:
        return client.open_by_key(key)
    except GoogleSheetsError:
        raise
    except PermissionError as exc:  # gspread 6: HTTP 403 -> PermissionError (bez treści)
        detail = str(exc) + " " + str(exc.__cause__ or "")
        if "has not been used" in detail or "is disabled" in detail:
            raise GoogleSheetsError(
                "Google Sheets API nie jest włączone w projekcie Google Cloud, z którego pochodzi klucz – "
                "włącz je (APIs & Services → Enabled APIs → Enable) i uruchom ponownie") from exc
        raise GoogleSheetsError(_no_access_message(key, credentials_path)) from exc
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        if name == "SpreadsheetNotFound":
            raise GoogleSheetsError(
                f"nie znaleziono arkusza o ID {key} – sprawdź ID skopiowane z adresu arkusza "
                f"(ciąg między /d/ a /edit)") from exc
        if "Connection" in name or "Timeout" in name or "SSL" in name:
            raise GoogleSheetsError(f"brak połączenia z Google ({name}) – sprawdź internet/zaporę i spróbuj ponownie") from exc
        raise GoogleSheetsError(f"błąd Google Sheets ({name}): {exc}") from exc


def push_sheets(
    spreadsheet_id: str,
    sheets: list[Sheet],
    credentials_path: str | None = None,
    client=None,
    reorder: bool = True,
    clear_stale: bool = True,
    now: datetime | None = None,
) -> PushResult:
    """Zapisuje każdą tabelę jako zakładkę (istniejąca o tej nazwie jest czyszczona).

    `client` – opcjonalnie gotowy klient gspread (do testów).
    Błędy dostępu (także 403 przy zapisie, gdy konto ma tylko rolę Przeglądający) i brak wpisu
    formuł (RAZEM, linki) zgłasza jako GoogleSheetsError; nieudane formatowanie tylko ostrzega
    (PushResult.formatting_error).
    """
    if client is None:
        import gspread  # import lokalny

        if not credentials_path:
            raise ValueError("podaj ścieżkę do klucza konta serwisowego (--credentials)")
        try:
            client = gspread.service_account(filename=credentials_path, http_client=gspread.BackOffHTTPClient)
        except Exception as exc:  # noqa: BLE001
            raise GoogleSheetsError(f"nie można wczytać klucza konta serwisowego {credentials_path}: {exc}") from exc
    sh = _open_spreadsheet(client, spreadsheet_id, credentials_path)
    try:
        return _push(sh, sheets, reorder=reorder, clear_stale=clear_stale, now=now)
    except GoogleSheetsError:
        raise
    except Exception as exc:  # noqa: BLE001
        if _http_status(exc) == 403:
            # odczyt się udał, zapis nie: arkusz udostępniony kontu serwisowemu tylko jako Przeglądający
            raise GoogleSheetsError(
                _no_access_message(extract_spreadsheet_id(spreadsheet_id), credentials_path)
                + " – arkusz jest widoczny, ale nie do zapisu: konto ma zapewne rolę Przeglądający, zmień ją na Edytor"
            ) from exc
        raise GoogleSheetsError(f"błąd zapisu do Google Sheets ({type(exc).__name__}): {exc}") from exc


def _push(sh, sheets: list[Sheet], reorder: bool, clear_stale: bool, now: datetime | None) -> PushResult:
    res = PushResult()
    # Google Sheets nie rozróżnia wielkości liter w nazwach zakładek ("DE oss" == "DE OSS")
    existing = {ws.title.casefold(): ws for ws in sh.worksheets()}
    used: set[str] = {ws.title.lower() for ws in existing.values()}
    written_keys: set[str] = set()
    ordered = []
    pending: list[tuple[Any, Sheet, int, bool]] = []   # (ws, sheet, liczba wierszy, reset formatów)
    for sheet in sheets:
        ws = existing.get(sheet.name.casefold())
        if ws is not None and ws.title.casefold() in written_keys:
            ws = None  # ta zakładka została już zapisana w tym przebiegu – druga tabela dostaje sufiks
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
        pending.append((ws, sheet, len(values), reset))
        res.written.append(name)
        written_keys.add(name.casefold())
        ordered.append(ws)
        log.info("Google Sheets: zakładka %s – %d wierszy", name, len(values))
    # formuły dopiero teraz: linki z „Wszystko” potrzebują sheetId zakładek utworzonych w tej pętli
    tabs = {sheet.name.casefold(): (ws.id, ws.title) for ws, sheet, _, _ in pending}
    formula_reqs: list[dict] = []
    format_reqs: list[dict] = []
    for ws, sheet, nvals, reset in pending:
        formula_reqs += _formula_requests(ws.id, sheet, tabs)
        format_reqs += _format_requests(ws.id, sheet, nvals, reset)
    if formula_reqs:
        try:
            sh.batch_update({"requests": formula_reqs})
        except Exception as exc:  # noqa: BLE001
            raise GoogleSheetsError(
                f"dane zapisane, ale formuły (wiersze RAZEM oraz linki w kolumnie „Zakładka” arkusza „Wszystko”) "
                f"nie zostały wpisane – uruchom ponownie; szczegóły: {exc}") from exc
    if format_reqs:
        try:
            sh.batch_update({"requests": format_reqs})
        except Exception as exc:  # noqa: BLE001 – formatowanie nie jest krytyczne
            res.formatting_error = str(exc)
            log.warning("dane i sumy zapisane, ale formatowanie zakładek (formaty liczb/dat, nagłówki) "
                        "nie powiodło się: %s", exc)
    if clear_stale:
        when = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
        note = STALE_NOTE.format(app=APP_NAME, when=when)
        for ws in list(existing.values()):
            if ws.title.casefold() in written_keys or not OWN_TAB_RE.match(ws.title):
                continue
            try:
                ws.clear()
                ws.update(values=[[note]], range_name="A1", value_input_option="RAW")
                res.cleared_stale.append(ws.title)
                log.info("Google Sheets: zakładka %s bez transakcji w tym uruchomieniu – wyczyszczona", ws.title)
            except Exception as exc:  # noqa: BLE001
                log.warning("nie udało się wyczyścić nieaktualnej zakładki %s: %s", ws.title, exc)
    if reorder and ordered:
        try:
            rest = [ws for ws in sh.worksheets() if ws.title not in res.written]
            sh.reorder_worksheets(ordered + rest)
        except Exception as exc:  # noqa: BLE001
            log.debug("reorder: %s", exc)
    return res
