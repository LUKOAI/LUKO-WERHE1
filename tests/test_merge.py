from datetime import date

from amazon_vat_merger.invoice_pdf import Address, Invoice, InvoiceItem
from amazon_vat_merger.merge import Formula, build_sheets, merge
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
    se = sheets[2]
    assert se.rows[0][0] == "Szwecja" and se.rows[0][1] == "OSS"
    header = se.rows[1]
    assert "Kwota netto SEK" in header and "Kwota VAT SEK" in header
    data = se.rows[2]
    assert data[header.index("Kwota netto SEK")] == 279.12 and data[header.index("Kwota netto EUR")] is None
    total = se.rows[-1]
    assert total[0] == "RAZEM" and isinstance(total[header.index("Kwota netto PLN")], Formula)
    assert total[header.index("Kwota netto PLN")].startswith("=SUM(")
    diag = sheets[-1]
    assert any(row[0] == "Brak PDF" for row in diag.rows)


def test_pln_transactions_do_not_duplicate_pln_columns():
    tx = _tx(**{"Currency": "PLN", "Marketplace ID": "PL", "Ship To Country": "PL", "Jurisdiction Name": "POLAND",
                "Tax Reporting Scheme": "", "Seller Tax Registration": "PL0000000000"})
    res = merge([tx], [], RateProvider(use_nbp=False))
    sheet = [s for s in build_sheets(res) if s.name == "PL Lokalna"][0]
    header = sheet.rows[1]
    assert header.count("Kwota netto PLN") == 1 and header.count("Kwota VAT PLN") == 1
    assert sheet.rows[2][header.index("Kwota netto PLN")] == 12.60
