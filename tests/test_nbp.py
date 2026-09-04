from datetime import date

from amazon_vat_merger.nbp import RateProvider


class FakeResp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_rates_file_previous_day(tmp_path):
    f = tmp_path / "kursy.csv"
    f.write_text("waluta;data;kurs\nEUR;2026-07-30;4,3000\nEUR;2026-07-31;4,3128\nEUR;2026-08-03;4,3200\n", encoding="utf-8")
    rp = RateProvider(use_nbp=False, rates_file=f)
    info = rp.get("EUR", date(2026, 8, 1))
    assert info.rate == 4.3128 and info.rate_date == date(2026, 7, 31) and info.source == "plik kursów"
    assert rp.get("EUR", date(2026, 7, 30)) is None
    assert rp.get("PLN", date(2026, 8, 1)).rate == 1.0
    assert rp.get("SEK", date(2026, 8, 1)) is None


def test_nbp_takes_last_rate_before_date():
    payload = {"rates": [
        {"no": "146/A/NBP/2026", "effectiveDate": "2026-07-30", "mid": 4.30},
        {"no": "147/A/NBP/2026", "effectiveDate": "2026-07-31", "mid": 4.3128},
    ]}
    sess = FakeSession([FakeResp(200, payload)])
    rp = RateProvider(session=sess)
    info = rp.get("EUR", date(2026, 8, 1))
    assert info.rate == 4.3128 and info.rate_date == date(2026, 7, 31) and info.source == "NBP 147/A/NBP/2026"
    assert "2026-07-20/2026-07-31" in sess.calls[0]
    # cache – drugi raz bez zapytania
    rp.get("EUR", date(2026, 8, 1))
    assert len(sess.calls) == 1


def test_nbp_failures_disable_after_limit():
    sess = FakeSession([RuntimeError("403"), RuntimeError("403"), RuntimeError("403"), FakeResp(200, {"rates": []})])
    rp = RateProvider(session=sess, max_failures=3)
    for d in (1, 2, 3, 4):
        assert rp.get("EUR", date(2026, 8, d)) is None
    assert len(sess.calls) == 3 and not rp.nbp_available and "403" in rp.last_error


def test_nbp_per_100_currency():
    sess = FakeSession([FakeResp(200, {"rates": [{"no": "1", "effectiveDate": "2026-08-03", "mid": 1.05}]})])
    rp = RateProvider(session=sess)
    assert rp.get("HUF", date(2026, 8, 4)).rate == 0.0105
