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
    ("3. März 2026", date(2026, 3, 3)),
    ("5 października 2026", date(2026, 10, 5)),
    ("12 février 2026", date(2026, 2, 12)),
    ("7. Jänner 2026", date(2026, 1, 7)),
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


@pytest.mark.skipif(not SAMPLES, reason="brak próbek PDF (samples/faktury)")
def test_all_sample_pdfs_against_csv():
    """Każda faktura z próbek: numer = nazwa pliku, zamówienie/kwota/ASIN zgodne z CSV."""
    from amazon_vat_merger.report import read_report
    from tests.conftest import SAMPLE_CSV
    if not SAMPLE_CSV.exists():
        pytest.skip("brak próbki CSV")
    txs = {}
    for t in read_report(SAMPLE_CSV):
        txs.setdefault(t.invoice_number, []).append(t)
    problems = []
    for path in SAMPLES:
        inv = parse_pdf(path)
        rows = txs.get(inv.invoice_number or "", [])
        if inv.invoice_number != path.stem:
            problems.append(f"{path.name}: numer {inv.invoice_number}")
        if not rows:
            continue  # PDF spoza raportu – dopuszczalne
        tx = rows[0]
        if len(rows) == 1 and (inv.invoice_total is None or abs(abs(inv.invoice_total) - abs(tx.total.gross)) > 0.011):
            problems.append(f"{path.name}: kwota PDF {inv.invoice_total} vs CSV {tx.total.gross}")
        if inv.currency != tx.currency:
            problems.append(f"{path.name}: waluta {inv.currency} vs {tx.currency}")
        if not any(it.asin == tx.asin for it in inv.items):
            problems.append(f"{path.name}: brak ASIN {tx.asin} w pozycjach {[i.asin for i in inv.items]}")
        if not inv.billing.name or not inv.billing.country:
            problems.append(f"{path.name}: brak adresu rozliczeniowego")
        if inv.invoice_date is None:
            problems.append(f"{path.name}: brak daty")
        if inv.is_credit_note != tx.is_negative:
            problems.append(f"{path.name}: typ {inv.doc_type} vs {tx.transaction_type}")
        if inv.is_credit_note and not inv.original_invoice_number:
            problems.append(f"{path.name}: nota bez numeru faktury pierwotnej")
        if inv.total_vat is not None and len(rows) == 1 and abs(abs(inv.total_vat) - abs(tx.total.vat)) > 0.011:
            problems.append(f"{path.name}: VAT PDF {inv.total_vat} vs CSV {tx.total.vat}")
        bad = [w for w in inv.warnings if "nie rozpoznano" in w or w.startswith("brak") or "różni się od 'do zapłaty'" in w]
        if bad:
            problems.append(f"{path.name}: {bad}")
    assert not problems, "\n".join(problems)


def test_thousands_with_space_and_currency_words():
    from amazon_vat_merger.invoice_pdf import Word, _numbers_from_words
    # "1 234,56 €" – odstęp jednej spacji między '1' a '234,56'
    words = [Word("1", 300, 304, 0), Word("234,56", 306, 340, 0), Word("€", 342, 348, 0)]
    nums = _numbers_from_words(words)
    assert nums["amounts"] == [1234.56] and nums["qty"] is None
    # ilość w osobnej kolumnie (duży odstęp) nie jest sklejana
    words = [Word("1", 300, 304, 0), Word("234,56", 360, 394, 0), Word("€", 396, 402, 0)]
    nums = _numbers_from_words(words)
    assert nums["qty"] == 1 and nums["amounts"] == [234.56]
    # 'von 30' to nie kwota w walucie VON
    assert amount_token("von30") is None and amount_token("Art194") is None
    assert amount_token("EUR12,50") == (12.5, "EUR")


def test_parse_amount_many_decimals():
    assert parse_amount("4,2345") == 4.2345
    assert parse_amount("1,234") == 1234.0      # tysiące
    assert parse_amount("1.234,5") == 1234.5


def _line(top, text, x0=344.0):
    from amazon_vat_merger.invoice_pdf import Line, Word
    words, x = [], x0
    for tok in text.split():
        words.append(Word(tok, x, x + 5 * len(tok), top))
        x += 5 * len(tok) + 4
    return Line(top=top, words=words)


def test_credit_note_number_chosen_without_filename_hint():
    from amazon_vat_merger.invoice_pdf import Invoice, _parse_header
    # FR: "Avoir pour la facture numéro X." przed "Numéro de l'avoir Y" i "... facture originale X"
    right = [_line(28, "Avoir", 532), _line(90, "Avoir pour la facture numéro FR6001ZYG6O6HI."),
             _line(160, "Numéro de l'avoir FR60005IG6O6HC"),
             _line(172, "Numéro de la facture originale FR6001ZYG6O6HI"), _line(186, "Total à payer -39,90 €")]
    inv = Invoice(file="x.pdf")
    _parse_header(right, [], inv, None)
    assert inv.invoice_number == "FR60005IG6O6HC" and inv.original_invoice_number == "FR6001ZYG6O6HI"
    assert inv.doc_type == "credit_note" and inv.total_to_pay == -39.9
    # DE: zdanie wprowadzające zawinięte – numer faktury pierwotnej w następnej linii
    right = [_line(28, "Rechnungskorrektur", 436), _line(90, "Dies ist eine Gutschrift / Rechnungskorrektur für die"),
             _line(104, "Rechnungsnummer DE6002GUG6O6HI"), _line(160, "Rechnungsdatum"), _line(170, "/Lieferdatum 29 August 2026"),
             _line(184, "Rechnungsnummer DE60006WG6O6HC"), _line(196, "Originalrechnungsnummer DE6002GUG6O6HI"),
             _line(210, "Zahlbetrag -13,99 €")]
    inv = Invoice(file="y.pdf")
    _parse_header(right, [], inv, None)
    assert inv.invoice_number == "DE60006WG6O6HC" and inv.original_invoice_number == "DE6002GUG6O6HI"
    assert inv.invoice_date == date(2026, 8, 29) and inv.total_to_pay == -13.99


def test_invoice_number_regex_with_underscores_and_vat_ids():
    from amazon_vat_merger.invoice_pdf import INVOICE_NO_RE, NON_INVOICE_TOKEN_RE
    assert INVOICE_NO_RE.search("PL600IIBG6O6HU_kopia".upper()).group(0) == "PL600IIBG6O6HU"
    assert INVOICE_NO_RE.search("faktura_PL600IIBG6O6HU.pdf".upper()).group(0) == "PL600IIBG6O6HU"
    assert NON_INVOICE_TOKEN_RE.match("NL123456789B01") and NON_INVOICE_TOKEN_RE.match("GB123456789012")


def test_wrapped_company_name_is_recovered_from_header_block():
    from amazon_vat_merger.invoice_pdf import _fix_wrapped_name
    billing = parse_address(["Przedsiębiorstwo Wielobranżowe", "Kowalski Sp. z o.o.", "Wspólna 2b/206", "Rzeszów, 35-205", "PL"])
    header = parse_address(["PRZEDSIĘBIORSTWO WIELOBRANŻOWE KOWALSKI SP. Z O.O.", "WSPÓLNA 2B/206", "RZESZÓW, 35-205", "PL"])
    _fix_wrapped_name(billing, header)
    assert billing.name == "Przedsiębiorstwo Wielobranżowe Kowalski Sp. z o.o."
    assert billing.street == "Wspólna 2b/206"
    # zwykły adres z dwiema liniami ulicy zostaje bez zmian
    billing = parse_address(["Daniel legg", "WOODLANDS COTTAGE, MINSTEAD", "LYNDHURST, SO43 7FY", "GB"])
    header = parse_address(["DANIEL LEGG", "WOODLANDS COTTAGE, MINSTEAD", "LYNDHURST, SO43 7FY", "GB"])
    _fix_wrapped_name(billing, header)
    assert billing.name == "Daniel legg" and billing.street == "WOODLANDS COTTAGE, MINSTEAD"
