from datetime import date

from amazon_vat_merger.gsheets import extract_spreadsheet_id, push_sheets, to_sheet_values
from amazon_vat_merger.merge import Formula, Sheet


class FakeWs:
    def __init__(self, title):
        self.title = title
        self.values = None
        self.cleared = False
        self.formats = []
        self.frozen = None

    def clear(self):
        self.cleared = True

    def resize(self, rows, cols):
        self.size = (rows, cols)

    def update(self, values, range_name, value_input_option):
        self.values = values
        self.range = range_name
        self.opt = value_input_option

    def format(self, rng, fmt):
        self.formats.append((rng, fmt))

    def batch_format(self, specs):
        self.formats.extend((s["range"], s["format"]) for s in specs)

    def freeze(self, rows, cols):
        self.frozen = (rows, cols)


class FakeSpreadsheet:
    def __init__(self, titles):
        self._ws = [FakeWs(t) for t in titles]
        self.order = None

    def worksheets(self):
        return list(self._ws)

    def add_worksheet(self, title, rows, cols):
        ws = FakeWs(title)
        self._ws.append(ws)
        return ws

    def reorder_worksheets(self, ws_list):
        self.order = [w.title for w in ws_list]


class FakeClient:
    def __init__(self, sh):
        self.sh = sh

    def open_by_key(self, key):
        self.key = key
        return self.sh


def test_to_sheet_values():
    rows = [[None, date(2026, 8, 1), 1.5, Formula("=SUM(A1:A2)"), "=nie formuła", True, "tekst"]]
    assert to_sheet_values(rows) == [["", "2026-08-01", 1.5, "=SUM(A1:A2)", "'=nie formuła", "TAK", "tekst"]]


def test_extract_id():
    url = "https://docs.google.com/spreadsheets/d/1EFgLol3XJESoDRb5uxZ-vtG1S5hMjNw__V-8h05KxgQ/edit?gid=7#gid=7"
    assert extract_spreadsheet_id(url) == "1EFgLol3XJESoDRb5uxZ-vtG1S5hMjNw__V-8h05KxgQ"
    assert extract_spreadsheet_id("abc") == "abc"


def test_push_sheets_creates_and_replaces():
    sh = FakeSpreadsheet(["Arkusz1", "DE OSS"])
    client = FakeClient(sh)
    sheets = [
        Sheet(name="Wszystko", rows=[["A", "B"], [1, date(2026, 1, 2)]], header_row=1, money_cols=[1]),
        Sheet(name="DE OSS", rows=[["Niemcy", "OSS"], ["A", "B"], [2, None], ["RAZEM", Formula("=SUM(B3:B3)")]], header_row=2, money_cols=[2]),
    ]
    written = push_sheets("https://docs.google.com/spreadsheets/d/XYZ/edit", sheets, client=client)
    assert written == ["Wszystko", "DE OSS"] and client.key == "XYZ"
    titles = [w.title for w in sh.worksheets()]
    assert titles == ["Arkusz1", "DE OSS", "Wszystko"]
    de = next(w for w in sh.worksheets() if w.title == "DE OSS")
    assert de.cleared and de.values[3] == ["RAZEM", "=SUM(B3:B3)"] and de.opt == "USER_ENTERED"
    assert de.frozen == (2, 1)
    assert sh.order == ["Wszystko", "DE OSS", "Arkusz1"]
