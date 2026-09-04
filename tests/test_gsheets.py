from datetime import date

from amazon_vat_merger.gsheets import extract_spreadsheet_id, push_sheets, to_sheet_values
from amazon_vat_merger.merge import Formula, Sheet


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
    def __init__(self, titles):
        self._ws = [FakeWs(t) for t in titles]
        self.order = None
        self.batches = []

    def worksheets(self):
        return list(self._ws)

    def add_worksheet(self, title, rows, cols):
        ws = FakeWs(title, rows, cols)
        self._ws.append(ws)
        return ws

    def batch_update(self, body):
        self.batches.append(body)

    def reorder_worksheets(self, ws_list):
        self.order = [w.title for w in ws_list]


class FakeClient:
    def __init__(self, sh):
        self.sh = sh

    def open_by_key(self, key):
        self.key = key
        return self.sh


def test_to_sheet_values():
    rows = [[None, date(2026, 8, 1), 1.5, Formula("=SUM(A1:A2)"), "=nie formuła", True, "tekst", "", "01234"]]
    assert to_sheet_values(rows) == [["", "2026-08-01", 1.5, "=SUM(A1:A2)", "'=nie formuła", "'TAK", "'tekst", "", "'01234"]]


def test_extract_id():
    url = "https://docs.google.com/spreadsheets/d/1EFgLol3XJESoDRb5uxZ-vtG1S5hMjNw__V-8h05KxgQ/edit?gid=7#gid=7"
    assert extract_spreadsheet_id(url) == "1EFgLol3XJESoDRb5uxZ-vtG1S5hMjNw__V-8h05KxgQ"
    assert extract_spreadsheet_id("abc") == "abc"


def test_push_sheets_creates_replaces_and_formats_in_one_batch():
    sh = FakeSpreadsheet(["Arkusz1", "DE OSS"])
    small = next(w for w in sh.worksheets() if w.title == "DE OSS")
    small.row_count, small.col_count = 3, 1
    client = FakeClient(sh)
    sheets = [
        Sheet(name="Wszystko", rows=[["A", "B"], [1, date(2026, 1, 2)]], header_row=1, money_cols=[1], date_cols=[2]),
        Sheet(name="DE OSS", rows=[["Niemcy", "OSS"], ["A", "B"], [2, None], ["RAZEM", Formula("=SUM(B3:B3)")]], header_row=2, money_cols=[2]),
    ]
    written = push_sheets("https://docs.google.com/spreadsheets/d/XYZ/edit", sheets, client=client)
    assert written == ["Wszystko", "DE OSS"] and client.key == "XYZ"
    titles = [w.title for w in sh.worksheets()]
    assert titles == ["Arkusz1", "DE OSS", "Wszystko"]
    de = next(w for w in sh.worksheets() if w.title == "DE OSS")
    assert de.cleared and de.values[3] == ["'RAZEM", "=SUM(B3:B3)"] and de.opt == "USER_ENTERED"
    assert de.resized is not None  # istniejąca zakładka była za mała
    # całe formatowanie w jednym batch_update
    assert len(sh.batches) == 1
    reqs = sh.batches[0]["requests"]
    kinds = [list(r)[0] for r in reqs]
    assert kinds.count("updateSheetProperties") == 2 and "repeatCell" in kinds
    frozen = [r["updateSheetProperties"]["properties"]["gridProperties"]["frozenRowCount"] for r in reqs if "updateSheetProperties" in r]
    assert sorted(frozen) == [1, 2]
    # reset formatów tylko dla istniejącej zakładki
    resets = [r for r in reqs if "repeatCell" in r and r["repeatCell"]["fields"] == "userEnteredFormat"]
    assert len(resets) == 1 and resets[0]["repeatCell"]["range"]["sheetId"] == de.id
    assert sh.order == ["Wszystko", "DE OSS", "Arkusz1"]
