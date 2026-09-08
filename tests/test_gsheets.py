import json
import logging
from datetime import date, datetime

import pytest

from amazon_vat_merger.gsheets import (
    GoogleSheetsError, extract_spreadsheet_id, push_sheets, to_sheet_values,
)
from amazon_vat_merger.merge import Formula, Link, Sheet


class FakeWs:
    _next_id = 100

    def __init__(self, title, rows=20, cols=10):
        self.title = title
        FakeWs._next_id += 1
        self.id = FakeWs._next_id
        self.row_count, self.col_count = rows, cols
        self.values = None
        self.cleared = False
        self.resized = None

    def clear(self):
        self.cleared = True

    def resize(self, rows, cols):
        self.resized = (rows, cols)
        self.row_count, self.col_count = rows, cols

    def update(self, values, range_name, value_input_option):
        self.values = values
        self.range = range_name
        self.opt = value_input_option


class FakeSpreadsheet:
    def __init__(self, titles, fail_batches=()):
        self._ws = [FakeWs(t) for t in titles]
        self.order = None
        self.batches = []
        self.fail_batches = set(fail_batches)   # numery (0-based) wywołań batch_update, które mają rzucić

    def worksheets(self):
        return list(self._ws)

    def add_worksheet(self, title, rows, cols):
        ws = FakeWs(title, rows, cols)
        self._ws.append(ws)
        return ws

    def batch_update(self, body):
        idx = len(self.batches)
        self.batches.append(body)
        if idx in self.fail_batches:
            raise RuntimeError(f"APIError: [500]: symulowany błąd batch #{idx}")

    def reorder_worksheets(self, ws_list):
        self.order = [w.title for w in ws_list]


class FakeClient:
    def __init__(self, sh):
        self.sh = sh

    def open_by_key(self, key):
        self.key = key
        return self.sh


def test_to_sheet_values_raw_mode():
    from amazon_vat_merger.gsheets import formula_cells
    rows = [[None, date(2026, 8, 1), 1.5, Formula("=SUM(A1:A2)"), "=nie formuła", True, "tekst", "", "01234"]]
    assert to_sheet_values(rows) == [["", 46235, 1.5, "", "=nie formuła", "TAK", "tekst", "", "01234"]]
    assert formula_cells(rows) == [(0, 3, "=SUM(A1:A2)")]
    # datetime (podklasa date) też przechodzi – bez TypeError na odejmowaniu
    assert to_sheet_values([[datetime(2026, 8, 1, 13, 45)]]) == [[46235]]
    # 1899-12-30 + 46235 dni == 2026-08-01
    from datetime import timedelta
    assert date(1899, 12, 30) + timedelta(days=46235) == date(2026, 8, 1)


def test_extract_id():
    url = "https://docs.google.com/spreadsheets/d/1EFgLol3XJESoDRb5uxZ-vtG1S5hMjNw__V-8h05KxgQ/edit?gid=7#gid=7"
    assert extract_spreadsheet_id(url) == "1EFgLol3XJESoDRb5uxZ-vtG1S5hMjNw__V-8h05KxgQ"
    assert extract_spreadsheet_id("abc") == "abc"


def test_push_sheets_creates_replaces_formulas_then_formatting():
    sh = FakeSpreadsheet(["Arkusz1", "DE OSS"])
    small = next(w for w in sh.worksheets() if w.title == "DE OSS")
    small.row_count, small.col_count = 3, 1
    client = FakeClient(sh)
    sheets = [
        Sheet(name="Wszystko", rows=[["A", "B"], [1, date(2026, 1, 2)]], header_row=1, money_cols=[1], date_cols=[2]),
        Sheet(name="DE OSS", rows=[["Niemcy", "OSS"], ["A", "B"], [2, None], ["RAZEM", Formula("=SUM(B3:B3)")]], header_row=2, money_cols=[2]),
    ]
    res = push_sheets("https://docs.google.com/spreadsheets/d/XYZ/edit", sheets, client=client)
    assert res.written == ["Wszystko", "DE OSS"] and client.key == "XYZ"
    assert res.cleared_stale == [] and res.formatting_error is None
    titles = [w.title for w in sh.worksheets()]
    assert titles == ["Arkusz1", "DE OSS", "Wszystko"]
    de = next(w for w in sh.worksheets() if w.title == "DE OSS")
    assert de.cleared and de.values[3] == ["RAZEM", ""] and de.opt == "RAW"
    assert de.resized is not None  # istniejąca zakładka była za mała
    # batch 1: tylko formuły (krytyczny), batch 2: całe formatowanie (niekrytyczny)
    assert len(sh.batches) == 2
    formulas = sh.batches[0]["requests"]
    assert [list(r)[0] for r in formulas] == ["updateCells"]
    assert formulas[0]["updateCells"]["start"] == {"sheetId": de.id, "rowIndex": 3, "columnIndex": 1}
    assert formulas[0]["updateCells"]["rows"][0]["values"][0]["userEnteredValue"]["formulaValue"] == "=SUM(B3:B3)"
    reqs = sh.batches[1]["requests"]
    kinds = [list(r)[0] for r in reqs]
    assert "updateCells" not in kinds
    assert kinds.count("updateSheetProperties") == 2 and "repeatCell" in kinds
    frozen = [r["updateSheetProperties"]["properties"]["gridProperties"]["frozenRowCount"] for r in reqs if "updateSheetProperties" in r]
    assert sorted(frozen) == [1, 2]
    # reset formatów tylko dla istniejącej zakładki
    resets = [r for r in reqs if "repeatCell" in r and r["repeatCell"]["fields"] == "userEnteredFormat"]
    assert len(resets) == 1 and resets[0]["repeatCell"]["range"]["sheetId"] == de.id
    assert sh.order == ["Wszystko", "DE OSS", "Arkusz1"]


def _razem_sheet(name="DE OSS"):
    return Sheet(name=name, rows=[["Niemcy", "OSS"], ["A", "B"], [2, 1.5], ["RAZEM", Formula("=SUM(B3:B3)")]],
                 header_row=2, money_cols=[2], pct_cols=[1])


def test_formula_batch_failure_is_an_error():
    sh = FakeSpreadsheet([], fail_batches=[0])
    with pytest.raises(GoogleSheetsError) as ei:
        push_sheets("XYZ", [_razem_sheet()], client=FakeClient(sh))
    assert "RAZEM" in str(ei.value) and "Zakładka" in str(ei.value) and "symulowany" in str(ei.value)


def test_formatting_batch_failure_only_warns(caplog):
    sh = FakeSpreadsheet([], fail_batches=[1])
    with caplog.at_level(logging.WARNING, logger="amazon_vat_merger.gsheets"):
        res = push_sheets("XYZ", [_razem_sheet()], client=FakeClient(sh))
    assert res.written == ["DE OSS"] and res.formatting_error and "symulowany" in res.formatting_error
    assert "dane i sumy zapisane" in caplog.text
    pct = [r for r in sh.batches[1]["requests"] if "repeatCell" in r
           and r["repeatCell"]["cell"].get("userEnteredFormat", {}).get("numberFormat", {}).get("type") == "PERCENT"]
    assert pct and pct[0]["repeatCell"]["cell"]["userEnteredFormat"]["numberFormat"]["pattern"] == "0.0%"


def test_stale_own_tabs_are_cleared_with_note_others_untouched():
    sh = FakeSpreadsheet(["Notatki księgowej", "DE OSS KOREKTA", "fr lokalna", "FR Lokalna KOREKTA"])
    res = push_sheets("XYZ", [Sheet(name="Wszystko", rows=[["A"], [1]], header_row=1),
                              Sheet(name="FR Lokalna", rows=[["A"], [1]], header_row=1)],
                      client=FakeClient(sh), now=datetime(2026, 9, 8, 12, 0))
    assert res.written == ["Wszystko", "fr lokalna"]
    assert res.cleared_stale == ["DE OSS KOREKTA", "FR Lokalna KOREKTA"]
    by = {w.title: w for w in sh.worksheets()}
    assert by["DE OSS KOREKTA"].cleared and by["DE OSS KOREKTA"].opt == "RAW"
    assert by["DE OSS KOREKTA"].values[0][0].startswith("Brak transakcji") and "2026-09-08 12:00" in by["DE OSS KOREKTA"].values[0][0]
    assert not by["Notatki księgowej"].cleared and by["Notatki księgowej"].values is None
    assert by["fr lokalna"].values == [["A"], [1]]


def test_same_run_name_collision_gets_suffix_instead_of_overwrite():
    sh = FakeSpreadsheet(["Arkusz1"])
    res = push_sheets("XYZ", [Sheet(name="DE OSS", rows=[["a"]], header_row=1),
                              Sheet(name="de OSS", rows=[["b"]], header_row=1)], client=FakeClient(sh))
    assert res.written == ["DE OSS", "de OSS (2)"]
    by = {w.title: w for w in sh.worksheets()}
    assert by["DE OSS"].values == [["a"]] and by["de OSS (2)"].values == [["b"]]


class _Raising:
    def __init__(self, exc):
        self.exc = exc

    def open_by_key(self, key):
        raise self.exc


class SpreadsheetNotFound(Exception):
    pass


def test_open_errors_are_translated(tmp_path):
    key = tmp_path / "klucz.json"
    key.write_text(json.dumps({"client_email": "luko-amafakt@projekt.iam.gserviceaccount.com"}), encoding="utf-8")
    with pytest.raises(GoogleSheetsError) as ei:
        push_sheets("ABC123", [], credentials_path=str(key), client=_Raising(PermissionError()))
    assert "ABC123" in str(ei.value) and "luko-amafakt@projekt.iam.gserviceaccount.com" in str(ei.value)
    with pytest.raises(GoogleSheetsError) as ei:
        push_sheets("ABC123", [], client=_Raising(SpreadsheetNotFound("<Response [404]>")))
    assert "nie znaleziono arkusza" in str(ei.value) and "ABC123" in str(ei.value)
    api_disabled = PermissionError()
    api_disabled.__cause__ = RuntimeError("APIError: [403]: Google Sheets API has not been used in project 1 before or it is disabled")
    with pytest.raises(GoogleSheetsError) as ei:
        push_sheets("ABC123", [], client=_Raising(api_disabled))
    assert "API nie jest włączone" in str(ei.value)


def test_existing_tab_matched_case_insensitively():
    sh = FakeSpreadsheet(["DE oss"])
    push_sheets("XYZ", [Sheet(name="DE OSS", rows=[["A"], [1]], header_row=1)], client=FakeClient(sh))
    titles = [w.title for w in sh.worksheets()]
    assert titles == ["DE oss"] and sh.worksheets()[0].cleared


def test_master_links_get_gid_and_are_grouped_into_one_request():
    sh = FakeSpreadsheet([])
    master = Sheet(name="Wszystko", rows=[["Zakładka", "X"],
                                          [Link("DE OSS", 4), 1], [Link("DE OSS", 5), 2], [Link("Nieistniejąca", 4), 3],
                                          ["tekst", 4], [Link("de oss", 6), 5]], header_row=1)
    de = Sheet(name="DE OSS", rows=[["Niemcy"], ["A"], [], [1], [2], [3], ["RAZEM", Formula("=SUM(A4:A6)")]], header_row=2)
    res = push_sheets("XYZ", [master, de], client=FakeClient(sh))
    assert res.written == ["Wszystko", "DE OSS"]
    ws = {w.title: w for w in sh.worksheets()}
    assert ws["Wszystko"].values[1] == ["", 1]   # link w wartościach pusty – wchodzi formułą
    reqs = sh.batches[0]["requests"]
    starts = [(r["updateCells"]["start"]["sheetId"], r["updateCells"]["start"]["rowIndex"], r["updateCells"]["start"]["columnIndex"], len(r["updateCells"]["rows"])) for r in reqs]
    # wiersze 1-3 kolumny A jednym żądaniem, wiersz 5 osobno (przerwa w wierszu 4), RAZEM w DE OSS osobno
    assert starts == [(ws["Wszystko"].id, 1, 0, 3), (ws["Wszystko"].id, 5, 0, 1), (ws["DE OSS"].id, 6, 1, 1)]
    vals = [v["values"][0]["userEnteredValue"] for v in reqs[0]["updateCells"]["rows"]]
    gid = ws["DE OSS"].id
    assert vals[0] == {"formulaValue": f'=HYPERLINK("#gid={gid}&range=A4","DE OSS")'}
    assert vals[1] == {"formulaValue": f'=HYPERLINK("#gid={gid}&range=A5","DE OSS")'}
    assert vals[2] == {"stringValue": "Nieistniejąca"}          # brak zakładki -> zwykły tekst
    assert reqs[1]["updateCells"]["rows"][0]["values"][0]["userEnteredValue"] == {"formulaValue": f'=HYPERLINK("#gid={gid}&range=A6","de oss")'}


def test_link_with_key_uses_actual_tab_title_in_match():
    sh = FakeSpreadsheet(["de oss"])   # istniejąca zakładka pisana małymi literami
    master = Sheet(name="Wszystko", rows=[["Zakładka"], [Link("DE OSS", 4, key="PL1")]], header_row=1)
    de = Sheet(name="DE OSS", rows=[["Niemcy"], ["A"], [], ["PL1"]], header_row=2)
    push_sheets("XYZ", [master, de], client=FakeClient(sh))
    ws = {w.title: w for w in sh.worksheets()}
    val = sh.batches[0]["requests"][0]["updateCells"]["rows"][0]["values"][0]["userEnteredValue"]["formulaValue"]
    assert val == f'=HYPERLINK("#gid={ws["de oss"].id}&range=A"&IFERROR(MATCH("PL1",\'de oss\'!A:A,0),4),"DE OSS")'


class APIError(Exception):
    def __init__(self, code):
        super().__init__(f"APIError: [{code}]: The caller does not have permission")
        self.code = code


def test_403_on_write_gets_sharing_hint(tmp_path):
    key = tmp_path / "klucz.json"
    key.write_text(json.dumps({"client_email": "sa@projekt.iam.gserviceaccount.com"}), encoding="utf-8")
    sh = FakeSpreadsheet(["Wszystko"])
    sh.worksheets()[0].clear = lambda: (_ for _ in ()).throw(APIError(403))   # odczyt OK, zapis 403 (rola Przeglądający)
    with pytest.raises(GoogleSheetsError) as ei:
        push_sheets("ABC", [Sheet(name="Wszystko", rows=[["A"]], header_row=1)], credentials_path=str(key), client=FakeClient(sh))
    msg = str(ei.value)
    assert "sa@projekt.iam.gserviceaccount.com" in msg and "Edytor" in msg and "Przeglądający" in msg and "ABC" in msg
    # inny kod HTTP -> komunikat ogólny
    sh2 = FakeSpreadsheet(["Wszystko"])
    sh2.worksheets()[0].clear = lambda: (_ for _ in ()).throw(APIError(500))
    with pytest.raises(GoogleSheetsError) as ei:
        push_sheets("ABC", [Sheet(name="Wszystko", rows=[["A"]], header_row=1)], client=FakeClient(sh2))
    assert "błąd zapisu do Google Sheets (APIError)" in str(ei.value)
