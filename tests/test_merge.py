from datetime import date

from amazon_vat_merger.invoice_pdf import Address, Invoice, InvoiceItem
from amazon_vat_merger.merge import Formula, build_sheets, merge, round2
from amazon_vat_merger.nbp import RateInfo, RateProvider
from amazon_vat_merger.report import transaction_from_row


def _tx(**over):
    base = {
        "Marketplace ID": "DE", "Order Date": "28-Aug-2026 UTC", "Shipment Date": "29-Aug-2026 UTC",
        "Transaction Type": "SHIPMENT", "Order ID": "111-1111111-1111111", "ASIN": "B000000001", "Quantity": "1",
        "Tax Rate": "0.1900", "Currency": "EUR", "Tax Reporting Scheme": "VCS_EU_OSS",
        "Tax Collection Responsibility": "Seller", "Jurisdiction Name": "GERMANY",
        "OUR_PRICE Tax Inclusive Selling Price": "14.99", "OUR_PRICE Tax Amount": "2.39",
        "OUR_PRICE Tax Exclusive Selling Price": "12.60", "Seller Tax Registration": "PL0000000000",
        "Seller Tax Registration Jurisdiction": "PL", "VAT Invoice Number": "PL6000000000AA",
        "Ship To Country": "DE", "Ship From Country": "PL", "Ship To City": "Fuerth", "Ship To Postal Code": "90766",
    }
    base.update(over)
    return transaction_from_row(base)


def _inv(number="PL6000000000AA", order="111-1111111-1111111", total=14.99, doc_type="invoice", asin="B000000001"):
    inv = Invoice(file=f"{number}.pdf", invoice_number=number, order_number=order, invoice_total=total, currency="EUR",
                  doc_type=doc_type, invoice_date=date(2026, 8, 29))
    inv.billing = Address(name="Max Mustermann", street="Hauptstr. 1", city="Fuerth", postal_code="90766",
                          country="DE", city_line="Fuerth, 90766", lines=["x"])
    inv.items = [InvoiceItem(description="Produkt", asin=asin, quantity=1, line_total=total)]
    return inv


class FixedRates(RateProvider):
    def __init__(self):
        super().__init__(use_nbp=False)

    def get(self, currency, ref_date):
        if currency == "PLN":
            return RateInfo(1.0, ref_date, "PLN")
        return RateInfo(4.3128, date(2026, 8, 28), "test")


def test_merge_by_invoice_number_and_pln():
    tx = _tx()
    res = merge([tx], [_inv()], FixedRates())
    r = res.rows[0]
    assert r.match == "PDF" and r.buyer_name == "Max Mustermann" and r.street == "Hauptstr. 1"
    assert r.city_line == "Fuerth, 90766"
    assert r.net_eur == 12.60 and r.vat_eur == 2.39
    assert r.net_pln == round(12.60 * 4.3128, 2) and r.rate_basis_date == date(2026, 8, 29)
    assert r.amount_check == "OK"
    assert r.item.description == "Produkt"
    assert res.matched == 1 and res.missing == 0 and not res.unmatched_invoices


def test_merge_missing_pdf_falls_back_to_csv_city():
    res = merge([_tx()], [], None)
    r = res.rows[0]
    assert r.match == "BRAK PDF" and r.buyer_name is None and r.city_line == "Fuerth, 90766"
    assert r.rate is None and r.net_pln is None


def test_merge_by_order_number_when_pdf_number_unknown():
    inv = _inv(number=None)
    res = merge([_tx()], [inv], None)
    assert res.rows[0].match == "PDF (po nr zamówienia)"


def test_credit_note_not_matched_to_shipment_by_order():
    inv = _inv(number=None, doc_type="credit_note")
    res = merge([_tx()], [inv], None)
    assert res.rows[0].match == "BRAK PDF" and res.unmatched_invoices == [inv]


def test_amount_mismatch_flagged_and_duplicates():
    inv1, inv2 = _inv(total=20.00), _inv()
    res = merge([_tx()], [inv1, inv2], None)
    assert res.rows[0].amount_check == "RÓŻNICA +5.01"
    assert len(res.duplicate_invoices) == 1


def test_amazon_csv_rate_fallback():
    tx = _tx(**{"Currency": "EUR", "Invoice Level Currency Code": "PLN", "Invoice Level Exchange Rate": "4.3268",
               "Invoice Level Exchange Rate Date": "26-Aug-2026 UTC", "Tax Reporting Scheme": "",
               "Buyer Tax Registration": "DE000000001", "Tax Rate": "0"})
    res = merge([tx], [], RateProvider(use_nbp=False))
    r = res.rows[0]
    assert r.rate.source == "Amazon (CSV)" and r.rate.rate == 4.3268 and r.rate.rate_date == date(2026, 8, 26)
    assert r.net_pln == round(12.60 * 4.3268, 2)
    assert tx.category == "WDT" and tx.tab_name == "PL WDT"


def test_build_sheets_structure():
    txs = [_tx(), _tx(**{"Currency": "SEK", "Marketplace ID": "SE", "Ship To Country": "SE",
                         "Jurisdiction Name": "SWEDEN", "VAT Invoice Number": "PL6000000000AB",
                         "Order ID": "222-2222222-2222222", "Tax Rate": "0.25",
                         "OUR_PRICE Tax Inclusive Selling Price": "348.90", "OUR_PRICE Tax Amount": "69.78",
                         "OUR_PRICE Tax Exclusive Selling Price": "279.12"})]
    res = merge(txs, [_inv()], FixedRates())
    sheets = build_sheets(res)
    names = [s.name for s in sheets]
    assert names == ["Wszystko", "DE OSS", "SE OSS", "Diagnostyka"]
    master = sheets[0]
    assert master.rows[0][0] == "Zakładka" and len(master.rows) == 3
    # kolumna „Zakładka” to link do wiersza transakcji w jej zakładce (dane od wiersza 4)
    from amazon_vat_merger.merge import Link
    links = sorted(master.rows[1:], key=lambda r: r[0].tab)
    assert all(isinstance(r[0], Link) for r in links)
    assert (links[0][0].tab, links[0][0].row, links[0][0].text) == ("DE OSS", 4, "DE OSS")
    assert str(links[1][0]) == '=HYPERLINK("#\'SE OSS\'!A4","SE OSS")'
    diag = sheets[3]
    assert diag.rows[0][0].startswith("LUKO AmaFakt v") and "support@netanaliza.com" in diag.rows[0][0]
    assert diag.rows[1] == ["Kategoria", "Element", "Szczegóły"] and diag.header_row == 2
    se = sheets[2]
    assert se.rows[0][:3] == ["", "Szwecja", "OSS"] and se.rows[2] == []      # wiersz 1 i pusty wiersz 3 jak u klienta
    header = se.rows[1]
    assert header[:14] == ["Numer faktury VAT", "Data zamówienia", "Data wysyłki", "Imię i nazwisko Kupującego", "Ulica",
                           "Miasto i kod pocztowy", "Kwota netto PLN", "Kwota netto EUR", "Kwota VAT EUR", "Kwota netto SEK",
                           "Kwota VAT SEK", "Stawka VAT", "Numer zamówienia", "System sprawozdawczości podatkowej"]
    assert se.extras_from == 15 and header[14] == "Kwota VAT PLN"
    data = se.rows[3]
    assert data[header.index("Kwota netto SEK")] == 279.12 and data[header.index("Kwota netto EUR")] is None
    assert data[header.index("Stawka VAT")] == 0.25
    total = se.rows[-1]
    assert total[0] == "RAZEM" and isinstance(total[header.index("Kwota netto PLN")], Formula)
    assert total[header.index("Kwota netto PLN")] == "=SUM(G4:G4)"
    de = sheets[1]
    assert de.rows[1][:12] == ["Numer faktury VAT", "Data zamówienia", "Data wysyłki", "Imię i nazwisko Kupującego", "Ulica",
                               "Miasto i kod pocztowy", "Kwota netto PLN", "Kwota netto EUR", "Stawka VAT", "Kwota należnego Vat'u",
                               "Numer zamówienia", "System sprawozdawczości podatkowej"]
    diag = sheets[-1]
    assert any(row[0] == "Brak PDF" for row in diag.rows)


def test_pln_transactions_do_not_duplicate_pln_columns():
    tx = _tx(**{"Currency": "PLN", "Marketplace ID": "PL", "Ship To Country": "PL", "Jurisdiction Name": "POLAND",
                "Tax Reporting Scheme": "", "Seller Tax Registration": "PL0000000000"})
    res = merge([tx], [], RateProvider(use_nbp=False))
    sheet = [s for s in build_sheets(res) if s.name == "PL Lokalna"][0]
    header = sheet.rows[1]
    assert header.count("Kwota netto PLN") == 1 and header.count("Kwota VAT PLN") == 1
    assert sheet.rows[3][header.index("Kwota netto PLN")] == 12.60


def test_pln_rounding_half_up_and_gross_consistency():
    assert round2(2.675) == 2.68 and round2(0.125) == 0.13 and round2(-2.675) == -2.68
    tx = _tx(**{"OUR_PRICE Tax Inclusive Selling Price": "15.23", "OUR_PRICE Tax Amount": "2.43",
                "OUR_PRICE Tax Exclusive Selling Price": "12.80"})
    res = merge([tx], [], FixedRates())
    r = res.rows[0]
    assert r.gross_pln == round2(r.net_pln + r.vat_pln)


def test_credit_note_uses_original_invoice_rate():
    sale = _tx()
    refund = _tx(**{"Transaction Type": "REFUND", "VAT Invoice Number": "PL6000000000CN", "Order Date": "12-Aug-2026 UTC",
                    "Shipment Date": "29-Sep-2026 UTC", "OUR_PRICE Tax Inclusive Selling Price": "-14.99",
                    "OUR_PRICE Tax Amount": "-2.39", "OUR_PRICE Tax Exclusive Selling Price": "-12.60"})

    class DatedRates(RateProvider):
        def __init__(self):
            super().__init__(use_nbp=False)

        def get(self, currency, ref_date):
            return RateInfo(4.0 if ref_date < date(2026, 9, 1) else 5.0, ref_date, "test")

    cn = _inv(number="PL6000000000CN", doc_type="credit_note", total=-14.99)
    cn.invoice_date = date(2026, 9, 29)
    cn.original_invoice_number = "PL6000000000AA"
    res = merge([sale, refund], [_inv(), cn], DatedRates())
    r_sale, r_ref = res.rows if res.rows[0].tx.invoice_number == "PL6000000000AA" else res.rows[::-1]
    assert r_sale.rate.rate == 4.0
    assert r_ref.rate.rate == 4.0 and "faktura pierwotna" in r_ref.rate.source and r_ref.rate_note
    assert r_ref.net_pln == round2(-12.60 * 4.0)
    # nota bez faktury pierwotnej w danych -> kurs z daty noty + uwaga
    res2 = merge([refund], [cn], DatedRates())
    assert res2.rows[0].rate.rate == 5.0 and res2.rows[0].rate_note.startswith("kurs z daty noty")


def test_rate_basis_is_earlier_of_invoice_and_shipment():
    tx = _tx(**{"Shipment Date": "29-Aug-2026 UTC"})
    inv = _inv(); inv.invoice_date = date(2026, 8, 31)
    res = merge([tx], [inv], FixedRates())
    assert res.rows[0].rate_basis_date == date(2026, 8, 29)
    inv.invoice_date = date(2026, 8, 27)
    res = merge([tx], [inv], FixedRates())
    assert res.rows[0].rate_basis_date == date(2026, 8, 27)


def test_multi_row_invoice_amount_check_uses_sum():
    tx1 = _tx()
    tx2 = _tx(**{"ASIN": "B000000002", "OUR_PRICE Tax Inclusive Selling Price": "10.00", "OUR_PRICE Tax Amount": "1.60",
                 "OUR_PRICE Tax Exclusive Selling Price": "8.40"})
    inv = _inv(total=24.99)
    inv.items.append(InvoiceItem(description="Drugi", asin="B000000002", quantity=1, line_total=10.0))
    res = merge([tx1, tx2], [inv], None)
    assert [r.amount_check for r in res.rows] == ["OK (suma 2 pozycji)"] * 2
    assert res.rows[1].item.description == "Drugi"
    inv.invoice_total = 20.00
    res = merge([tx1, tx2], [inv], None)
    assert res.rows[0].amount_check == "RÓŻNICA -4.99 (suma 2 pozycji)"
    diag = [s for s in build_sheets(res) if s.name == "Diagnostyka"][0]
    assert sum(1 for r in diag.rows if r[0] == "Kwota PDF ≠ CSV") == 1


def test_missing_pdf_total_flagged():
    inv = _inv(total=None)
    res = merge([_tx()], [inv], None)
    assert res.rows[0].amount_check == "BRAK SUMY W PDF"


def test_order_fallback_refused_when_order_has_two_invoices():
    tx1 = _tx()
    tx2 = _tx(**{"VAT Invoice Number": "PL6000000000AB", "ASIN": "B000000002"})
    inv = _inv(number=None)   # PDF bez numeru, ten sam nr zamówienia
    res = merge([tx1, tx2], [inv], None)
    assert all(r.invoice is None for r in res.rows)
    assert res.rows[0].match.startswith("BRAK PDF (1 kandydat")
    assert res.ambiguous and res.unmatched_invoices == [inv]


def test_duplicate_pdf_not_reported_as_unmatched():
    res = merge([_tx()], [_inv(), _inv()], None)
    assert len(res.duplicate_invoices) == 1 and res.unmatched_invoices == []


def test_rows_without_invoice_number_are_grouped_per_order():
    tx = _tx(**{"VAT Invoice Number": ""})
    res = merge([tx], [_inv(number=None)], None)
    assert res.rows[0].match == "PDF (po nr zamówienia)" and res.rows[0].amount_check == "OK"


def test_corrections_go_to_separate_tabs():
    sale = _tx()
    refund = _tx(**{"Transaction Type": "REFUND", "VAT Invoice Number": "PL6000000000CN",
                    "OUR_PRICE Tax Inclusive Selling Price": "-14.99", "OUR_PRICE Tax Amount": "-2.39",
                    "OUR_PRICE Tax Exclusive Selling Price": "-12.60"})
    assert sale.tab_name == "DE OSS" and refund.tab_name == "DE OSS KOREKTA"
    sheets = build_sheets(merge([sale, refund], [], None))
    names = [s.name for s in sheets]
    assert names == ["Wszystko", "DE OSS", "DE OSS KOREKTA", "Diagnostyka"]
    kor = sheets[2]
    assert kor.rows[0][1] == "Niemcy" and kor.rows[0][2] == "OSS KOREKTA" and kor.rows[0][3].startswith("korekty")
    assert kor.rows[3][kor.rows[1].index("Kwota netto EUR")] == -12.60
