from datetime import date

import pytest

from amazon_vat_merger.invoice_pdf import amount_token, parse_address, parse_amount, parse_date_text, parse_pdf
from tests.conftest import SAMPLE_PDF_DIR


@pytest.mark.parametrize("s,v", [
    ("121,87", 121.87), ("1.234,56", 1234.56), ("12.90", 12.9), ("-3,99", -3.99),
    ("1 234,56", 1234.56), ("0,00", 0.0), ("17,9", 17.9), ("abc", None), ("1,234.56", 1234.56),
])
def test_parse_amount(s, v):
    assert parse_amount(s) == v


def test_amount_token():
    assert amount_token("CZK0.00") == (0.0, "CZK")
    assert amount_token("€12,90") == (12.9, "EUR")
    assert amount_token("17,90€") == (17.9, "EUR")
    assert amount_token("121,87zł") == (121.87, "PLN")
    assert amount_token("1") is None            # ilość, nie kwota
    assert amount_token("2026") is None
    assert amount_token("279,12kr") == (279.12, "SEK")


@pytest.mark.parametrize("s,d", [
    ("29 sierpnia 2026", date(2026, 8, 29)),
    ("29 agosto 2026", date(2026, 8, 29)),
    ("29 août 2026", date(2026, 8, 29)),
    ("29. August 2026", date(2026, 8, 29)),
    ("29 de agosto de 2026", date(2026, 8, 29)),
    ("29 augustus 2026", date(2026, 8, 29)),
    ("29 augusti 2026", date(2026, 8, 29)),
    ("August 29, 2026", date(2026, 8, 29)),
    ("29/08/2026", date(2026, 8, 29)),
    ("29.08.2026", date(2026, 8, 29)),
    ("2026-08-29", date(2026, 8, 29)),
    ("1 mars 2026", date(2026, 3, 1)),
    ("brak daty", None),
])
def test_parse_date_text(s, d):
    assert parse_date_text(s) == d


def test_parse_address_with_vat_in_street():
    a = parse_address(["Stylem sp. z o.o.", "Wspólna, 2b/206, NIP PL5170372051", "Rzeszów, 35-205", "PL"])
    assert a.name == "Stylem sp. z o.o."
    assert a.street == "Wspólna, 2b/206"
    assert a.vat_id == "PL5170372051"
    assert a.city == "Rzeszów" and a.postal_code == "35-205" and a.country == "PL"


def test_parse_address_region_and_two_street_lines():
    a = parse_address(["Jan Kowalski", "Hauptstr. 5", "Hinterhaus", "Berlin, Berlin, 10115", "DE", "USt-IdNr. DE123456789"])
    assert a.street == "Hauptstr. 5, Hinterhaus"
    assert a.region == "Berlin" and a.postal_code == "10115" and a.city == "Berlin"
    assert a.vat_id == "DE123456789"


def test_parse_address_no_country_line():
    a = parse_address(["Anna", "Rue 1", "Paris, 75001"])
    assert a.country is None and a.city == "Paris" and a.postal_code == "75001"
    assert parse_address([]).empty


SAMPLES = sorted(SAMPLE_PDF_DIR.glob("*.pdf")) if SAMPLE_PDF_DIR.exists() else []


@pytest.mark.skipif(not SAMPLES, reason="brak próbek PDF (samples/faktury)")
def test_sample_pdfs_parse():
    expected = {
        "CZ60009FG6O6HI": dict(order="403-5010410-6904344", total=121.87, cur="PLN", lang="pl", asin="B09DL93LXM",
                               buyer_vat="PL5170372051", conv=("CZK", 0.0), net=121.87, vat=0.0, rate=0.0),
        "FR600230G6O6HI": dict(order="402-5510833-0676369", total=17.90, cur="EUR", lang="fr", asin="B01K5NO9LW",
                               buyer_vat=None, conv=None, net=14.92, vat=2.98, rate=20.0),
        "IT600249G6O6HT": dict(order="404-0509060-1244347", total=12.90, cur="EUR", lang="it", asin="B0DNTJ212Y",
                               buyer_vat=None, conv=None, net=None, vat=None, rate=None),
        "IT60024DG6O6HT": dict(order="407-0047945-9822739", total=18.98, cur="EUR", lang="it", asin="B0BBGB6LCB",
                               buyer_vat=None, conv=None, net=None, vat=None, rate=None),
    }
    for path in SAMPLES:
        inv = parse_pdf(path)
        exp = expected.get(inv.invoice_number)
        if exp is None:
            continue
        assert inv.invoice_number == path.stem
        assert inv.order_number == exp["order"]
        assert inv.invoice_total == exp["total"] and inv.currency == exp["cur"]
        assert inv.language == exp["lang"]
        assert inv.invoice_date == date(2026, 8, 29)
        assert inv.doc_type == "invoice" and inv.paid is True
        assert inv.billing.name and inv.billing.country and inv.billing.postal_code
        assert inv.buyer_header.name.upper() == inv.billing.name.upper()
        assert inv.buyer_vat_id == exp["buyer_vat"]
        assert inv.seller_name == "Gaj Wioletta"
        assert [it.asin for it in inv.items] == [exp["asin"]]
        assert inv.items[0].description and "ASIN" not in inv.items[0].description
        assert inv.items[0].quantity == 1
        if exp["conv"]:
            assert (inv.converted_vat_currency, inv.converted_vat_amount) == exp["conv"]
        if exp["net"] is not None:
            assert inv.total_net == exp["net"] and inv.total_vat == exp["vat"]
            assert inv.vat_lines and inv.vat_lines[0].rate == exp["rate"]
        assert not [w for w in inv.warnings if "nie rozpoznano" in w or "brak" in w], inv.warnings
