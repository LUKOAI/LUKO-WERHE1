"""Łączenie transakcji z CSV z fakturami PDF i budowa arkuszy (tabel)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable

from . import labels as L
from .invoice_pdf import Invoice, InvoiceItem
from .nbp import RateInfo, RateProvider
from .report import CATEGORY_DESCRIPTION, Transaction

log = logging.getLogger(__name__)

DOC_TYPE_PL = {"invoice": "Faktura", "credit_note": "Nota kredytowa", "unknown": ""}


def round2(value: float | None) -> float | None:
    """Zaokrąglenie księgowe (HALF_UP) do 2 miejsc – round() Pythona zaokrągla 'do parzystej'."""
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
PAYMENT_STATUS_PL = {"paid": "Zapłacono", "refunded": "Zwrócono", "due": "Do zapłaty"}


@dataclass
class MergedRow:
    tx: Transaction
    invoice: Invoice | None = None
    item: InvoiceItem | None = None
    match: str = "BRAK PDF"
    rate: RateInfo | None = None
    rate_basis_date: date | None = None
    net_pln: float | None = None
    vat_pln: float | None = None
    gross_pln: float | None = None
    net_eur: float | None = None
    vat_eur: float | None = None
    amount_check: str = ""
    rate_note: str = ""

    # ---- wygodne gettery ----
    @property
    def buyer_name(self) -> str | None:
        return self.invoice.buyer_name if self.invoice else None

    @property
    def street(self) -> str | None:
        if not self.invoice:
            return None
        return self.invoice.billing.street or self.invoice.buyer_header.street

    @property
    def city_line(self) -> str | None:
        if self.invoice:
            cl = self.invoice.billing.city_line or self.invoice.buyer_header.city_line
            if cl:
                return cl
        tx = self.tx
        if tx.ship_to_city or tx.ship_to_postal:
            return f"{tx.ship_to_city}, {tx.ship_to_postal}".strip(", ")
        return None

    @property
    def postal_code(self) -> str | None:
        if self.invoice and (self.invoice.billing.postal_code or self.invoice.buyer_header.postal_code):
            return self.invoice.billing.postal_code or self.invoice.buyer_header.postal_code
        return self.tx.ship_to_postal or None

    @property
    def city(self) -> str | None:
        if self.invoice and (self.invoice.billing.city or self.invoice.buyer_header.city):
            return self.invoice.billing.city or self.invoice.buyer_header.city
        return self.tx.ship_to_city or None

    @property
    def billing_country(self) -> str | None:
        if self.invoice:
            return self.invoice.billing.country or self.invoice.buyer_header.country
        return None


@dataclass
class MergeResult:
    rows: list[MergedRow]
    invoices: list[Invoice]
    unmatched_invoices: list[Invoice] = field(default_factory=list)
    duplicate_invoices: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    rate_provider: RateProvider | None = None
    csv_duplicates: int = 0

    @property
    def matched(self) -> int:
        return sum(1 for r in self.rows if r.invoice is not None)

    @property
    def missing(self) -> int:
        return sum(1 for r in self.rows if r.invoice is None)


# ---------------------------------------------------------------------------
# łączenie
# ---------------------------------------------------------------------------
def _basis_date(tx: Transaction, inv: Invoice | None, basis: str) -> date | None:
    if basis == "order":
        return tx.order_date or tx.shipment_date
    if basis == "shipment":
        return tx.shipment_date or tx.order_date
    # invoice (domyślnie): obowiązek podatkowy = dostawa (data wysyłki), chyba że faktura
    # wystawiona wcześniej (art. 31a ust. 2) -> wcześniejsza z dat faktury (PDF) i wysyłki
    cands = [d for d in ((inv.invoice_date if inv else None), tx.shipment_date) if d]
    if cands:
        return min(cands)
    return tx.order_date


def _apply_rates(row: MergedRow, rates: RateProvider | None, basis: str, original: "MergedRow | None" = None) -> None:
    tx = row.tx
    row.rate_basis_date = _basis_date(tx, row.invoice, basis)
    info = None
    if original is not None and original.rate is not None:
        # nota kredytowa: kurs faktury pierwotnej (art. 31b ust. 1 ustawy o VAT)
        info = RateInfo(original.rate.rate, original.rate.rate_date, f"{original.rate.source} (faktura pierwotna {original.tx.invoice_number})")
        row.rate_basis_date = original.rate_basis_date
        row.rate_note = f"kurs faktury pierwotnej {original.tx.invoice_number}"
    if info is None and rates is not None:
        info = rates.get(tx.currency, row.rate_basis_date)
    if info is None and tx.invoice_currency == "PLN" and tx.invoice_exchange_rate:
        info = RateInfo(tx.invoice_exchange_rate, tx.invoice_exchange_rate_date or row.rate_basis_date, "Amazon (CSV)")
    row.rate = info
    if info:
        row.net_pln = round2(tx.total.net * info.rate)
        row.vat_pln = round2(tx.total.vat * info.rate)
        row.gross_pln = round2(row.net_pln + row.vat_pln)
    # EUR
    if tx.currency == "EUR":
        row.net_eur, row.vat_eur = tx.total.net, tx.total.vat
    elif tx.invoice_currency == "EUR" and tx.converted_tax_amount is not None and tx.invoice_exchange_rate:
        row.vat_eur = tx.converted_tax_amount
        row.net_eur = round(tx.total.net * tx.invoice_exchange_rate, 2)
    elif row.invoice and row.invoice.converted_vat_currency == "EUR" and row.invoice.converted_vat_amount is not None:
        row.vat_eur = row.invoice.converted_vat_amount


def _inv_key(tx: Transaction) -> str:
    """Klucz grupowania wierszy CSV w jedną fakturę (wiersze bez numeru – per zamówienie i typ)."""
    return tx.invoice_number or f"order:{tx.order_id}:{tx.transaction_type}"


def _amount_check(row: MergedRow, rows_per_invoice: int, gross_sum: float) -> str:
    inv = row.invoice
    if inv is None:
        return ""
    if inv.invoice_total is None:
        return "BRAK SUMY W PDF"
    diff = round2(abs(inv.invoice_total) - abs(gross_sum))
    suffix = f" (suma {rows_per_invoice} pozycji)" if rows_per_invoice > 1 else ""
    if abs(diff) < 0.011:
        return "OK" + suffix
    return f"RÓŻNICA {diff:+.2f}" + suffix


def merge(
    transactions: list[Transaction],
    invoices: list[Invoice],
    rates: RateProvider | None = None,
    rate_basis: str = "invoice",
) -> MergeResult:
    by_number: dict[str, Invoice] = {}
    dups: list[str] = []
    for inv in invoices:
        if not inv.invoice_number:
            continue
        key = inv.invoice_number.upper()
        if key in by_number:
            dups.append(f"{inv.file} (duplikat {by_number[key].file})")
            continue
        by_number[key] = inv
    by_order: dict[str, list[Invoice]] = {}
    for inv in invoices:
        if inv.order_number:
            by_order.setdefault(inv.order_number, []).append(inv)

    dup_ids = {id(inv) for inv in invoices if inv.invoice_number and by_number.get(inv.invoice_number.upper()) is not inv}
    used: set[int] = set()
    rows: list[MergedRow] = []
    per_invoice: dict[str, int] = {}
    gross_per_invoice: dict[str, float] = {}
    vat_per_invoice: dict[str, float] = {}
    numbers_per_order: dict[tuple[str, bool], set[str]] = {}
    for tx in transactions:
        k = _inv_key(tx)
        per_invoice[k] = per_invoice.get(k, 0) + 1
        gross_per_invoice[k] = round2(gross_per_invoice.get(k, 0.0) + tx.total.gross)
        vat_per_invoice[k] = round2(vat_per_invoice.get(k, 0.0) + tx.total.vat)
        numbers_per_order.setdefault((tx.order_id, tx.is_negative), set()).add(tx.invoice_number)
    ambiguous: list[str] = []
    for tx in transactions:
        row = MergedRow(tx=tx)
        inv = by_number.get(tx.invoice_number) if tx.invoice_number else None
        if inv is not None:
            row.match = "PDF"
        elif tx.order_id:
            cands = [
                c for c in by_order.get(tx.order_id, [])
                if (not c.invoice_number or c.invoice_number.upper() not in by_number)
                and ((c.doc_type == "credit_note") == tx.is_negative)
            ]
            distinct_numbers = numbers_per_order.get((tx.order_id, tx.is_negative), set())
            if len(cands) == 1 and len(distinct_numbers) <= 1:
                inv = cands[0]
                row.match = "PDF (po nr zamówienia)"
            elif cands:
                row.match = f"BRAK PDF ({len(cands)} kandydatów po nr zamówienia)"
                ambiguous.append(f"{tx.invoice_number or tx.order_id}: {', '.join(c.file for c in cands)}")
        row.invoice = inv
        if inv is not None:
            used.add(id(inv))
            if inv.items:
                row.item = next((it for it in inv.items if it.asin and it.asin == tx.asin), None)
                if row.item is None and len(inv.items) == 1:
                    row.item = inv.items[0]
        k = _inv_key(tx)
        row.amount_check = _amount_check(row, per_invoice.get(k, 1), gross_per_invoice.get(k, tx.total.gross))
        rows.append(row)
    # kursy: najpierw sprzedaż, potem zwroty (kurs faktury pierwotnej, jeśli jest w danych)
    by_invoice: dict[str, MergedRow] = {}
    for row in rows:
        if not row.tx.is_negative:
            _apply_rates(row, rates, rate_basis)
            by_invoice.setdefault(row.tx.invoice_number, row)
    for row in rows:
        if row.tx.is_negative:
            orig_no = (row.invoice.original_invoice_number if row.invoice else None) or row.tx.original_invoice_number
            original = by_invoice.get(orig_no) if orig_no else None
            _apply_rates(row, rates, rate_basis, original)
            if original is None and row.tx.currency != "PLN":
                row.rate_note = (
                    f"kurs z daty noty – faktura pierwotna {orig_no} poza danymi" if orig_no
                    else "kurs z daty noty – brak numeru faktury pierwotnej"
                )
    unmatched = [inv for inv in invoices if id(inv) not in used and id(inv) not in dup_ids]
    log.info("dopasowano %d/%d transakcji do PDF; PDF bez transakcji: %d", sum(1 for r in rows if r.invoice), len(rows), len(unmatched))
    return MergeResult(rows=rows, invoices=invoices, unmatched_invoices=unmatched, duplicate_invoices=dups,
                       ambiguous=ambiguous, rate_provider=rates)


# ---------------------------------------------------------------------------
# tabele (wspólne dla xlsx i Google Sheets)
# ---------------------------------------------------------------------------
class Formula(str):
    """Wartość komórki będąca formułą (=SUM(...))."""


@dataclass
class Sheet:
    name: str
    rows: list[list[Any]]                    # wszystkie wiersze łącznie z tytułem i nagłówkiem
    header_row: int = 1                      # 1-based indeks wiersza nagłówka
    money_cols: list[int] = field(default_factory=list)   # 1-based kolumny kwot
    date_cols: list[int] = field(default_factory=list)
    pct_cols: list[int] = field(default_factory=list)
    widths: dict[int, float] = field(default_factory=dict)


def _pdf_addr_line(inv: Invoice | None) -> str | None:
    if not inv or inv.shipping.empty:
        return None
    parts = [inv.shipping.street, inv.shipping.city_line, inv.shipping.country]
    return ", ".join(p for p in parts if p)


def _pct(v: float | None) -> float | None:
    return None if v is None else round(v * 100, 2)


MASTER_COLUMNS: list[tuple[str, Callable[[MergedRow], Any], str]] = [
    # (nagłówek, getter, typ: s=tekst, m=kwota, d=data, p=procent)
    ("Zakładka", lambda r: r.tx.tab_name, "s"),
    ("Kategoria", lambda r: r.tx.category, "s"),
    ("Numer faktury VAT", lambda r: r.tx.invoice_number, "s"),
    ("Typ dokumentu (PDF)", lambda r: DOC_TYPE_PL.get(r.invoice.doc_type, "") if r.invoice else "", "s"),
    ("Typ transakcji", lambda r: r.tx.transaction_type_pl, "s"),
    ("Data zamówienia", lambda r: r.tx.order_date, "d"),
    ("Data wysyłki", lambda r: r.tx.shipment_date, "d"),
    ("Data faktury (PDF)", lambda r: r.invoice.invoice_date if r.invoice else None, "d"),
    ("Data naliczenia podatku (CSV)", lambda r: r.tx.tax_calculation_date, "d"),
    ("Data dostawy (PDF)", lambda r: r.invoice.delivery_date if r.invoice else None, "d"),
    ("Faktura pierwotna (PDF)", lambda r: r.invoice.original_invoice_number if r.invoice else None, "s"),
    ("Status płatności (PDF)", lambda r: PAYMENT_STATUS_PL.get(r.invoice.payment_status or "", "") if r.invoice else "", "s"),
    ("Numer zamówienia", lambda r: r.tx.order_id, "s"),
    ("Marketplace", lambda r: r.tx.marketplace, "s"),
    ("Imię i nazwisko Kupującego", lambda r: r.buyer_name, "s"),
    ("Ulica", lambda r: r.street, "s"),
    ("Miasto i kod pocztowy", lambda r: r.city_line, "s"),
    ("Kod pocztowy", lambda r: r.postal_code, "s"),
    ("Miasto", lambda r: r.city, "s"),
    ("Kraj (adres rozliczeniowy)", lambda r: r.billing_country, "s"),
    ("NIP nabywcy (PDF)", lambda r: r.invoice.buyer_vat_id if r.invoice else None, "s"),
    ("NIP nabywcy (CSV)", lambda r: r.tx.buyer_vat, "s"),
    ("Odbiorca dostawy (PDF)", lambda r: r.invoice.shipping.name if r.invoice else None, "s"),
    ("Adres dostawy (PDF)", lambda r: _pdf_addr_line(r.invoice), "s"),
    ("Kraj dostawy", lambda r: r.tx.ship_to_country, "s"),
    ("Miasto dostawy (CSV)", lambda r: r.tx.ship_to_city, "s"),
    ("Kod pocztowy dostawy (CSV)", lambda r: r.tx.ship_to_postal, "s"),
    ("Kraj wysyłki (magazyn)", lambda r: r.tx.ship_from_country, "s"),
    ("Miasto wysyłki (magazyn)", lambda r: r.tx.ship_from_city, "s"),
    ("Kraj wysyłki (PDF)", lambda r: (r.invoice.shipped_from_country or r.invoice.shipped_from) if r.invoice else None, "s"),
    ("NIP sprzedawcy", lambda r: r.tx.seller_vat, "s"),
    ("Kraj rejestracji sprzedawcy", lambda r: r.tx.seller_jurisdiction, "s"),
    ("Jurysdykcja podatkowa", lambda r: r.tx.jurisdiction_name, "s"),
    ("System sprawozdawczości podatkowej", lambda r: r.tx.scheme, "s"),
    ("Odpowiedzialność za VAT", lambda r: r.tx.collection_responsibility, "s"),
    ("Eksport poza UE (CSV)", lambda r: "TAK" if r.tx.export_outside_eu else "", "s"),
    ("Waluta", lambda r: r.tx.currency, "s"),
    ("Stawka VAT %", lambda r: r.tx.tax_rate_pct, "p"),
    ("Kwota netto", lambda r: r.tx.total.net, "m"),
    ("Kwota VAT", lambda r: r.tx.total.vat, "m"),
    ("Kwota brutto", lambda r: r.tx.total.gross, "m"),
    ("Netto towar", lambda r: r.tx.item.net, "m"),
    ("VAT towar", lambda r: r.tx.item.vat, "m"),
    ("Netto wysyłka", lambda r: r.tx.shipping.net, "m"),
    ("VAT wysyłka", lambda r: r.tx.shipping.vat, "m"),
    ("Netto opakowanie", lambda r: r.tx.giftwrap.net, "m"),
    ("VAT opakowanie", lambda r: r.tx.giftwrap.vat, "m"),
    ("Kwota netto EUR", lambda r: r.net_eur, "m"),
    ("Kwota VAT EUR", lambda r: r.vat_eur, "m"),
    ("Kurs PLN", lambda r: r.rate.rate if r.rate else None, "s"),
    ("Data kursu", lambda r: r.rate.rate_date if r.rate else None, "d"),
    ("Źródło kursu", lambda r: r.rate.source if r.rate else None, "s"),
    ("Data bazowa kursu", lambda r: r.rate_basis_date, "d"),
    ("Uwaga do kursu", lambda r: r.rate_note or None, "s"),
    ("Kwota netto PLN", lambda r: r.net_pln, "m"),
    ("Kwota VAT PLN", lambda r: r.vat_pln, "m"),
    ("Kwota brutto PLN", lambda r: r.gross_pln, "m"),
    ("ASIN", lambda r: r.tx.asin, "s"),
    ("SKU", lambda r: r.tx.sku, "s"),
    ("Ilość", lambda r: r.tx.quantity, "s"),
    ("Opis produktu (PDF)", lambda r: r.item.description if r.item else None, "s"),
    ("Kwota faktury (PDF)", lambda r: r.invoice.invoice_total if r.invoice else None, "m"),
    ("Netto wg PDF", lambda r: r.invoice.total_net if r.invoice else None, "m"),
    ("VAT wg PDF", lambda r: r.invoice.total_vat if r.invoice else None, "m"),
    ("Rabat (PDF)", lambda r: r.invoice.discount_gross if r.invoice else None, "m"),
    ("Uwagi z faktury (PDF)", lambda r: " | ".join(r.invoice.notes) if r.invoice and r.invoice.notes else None, "s"),
    ("Waluta (PDF)", lambda r: r.invoice.currency if r.invoice else None, "s"),
    ("Zgodność kwoty PDF/CSV", lambda r: r.amount_check, "s"),
    ("VAT w walucie rejestracji (PDF)", lambda r: (
        f"{r.invoice.converted_vat_currency} {r.invoice.converted_vat_amount:.2f}"
        if r.invoice and r.invoice.converted_vat_currency and r.invoice.converted_vat_amount is not None else None), "s"),
    ("Referencja płatności (PDF)", lambda r: r.invoice.payment_reference if r.invoice else None, "s"),
    ("Plik PDF", lambda r: r.invoice.file if r.invoice else None, "s"),
    ("Dopasowanie PDF", lambda r: r.match, "s"),
    ("Ostrzeżenia PDF", lambda r: "; ".join(r.invoice.warnings) if r.invoice and r.invoice.warnings else None, "s"),
    ("Link do faktury (Seller Central)", lambda r: r.tx.invoice_url, "s"),
    ("Faktura pierwotna (korekta)", lambda r: r.tx.original_invoice_number, "s"),
    ("Nr KSeF", lambda r: r.tx.ksef_number, "s"),
    ("Status e-faktury", lambda r: r.tx.einvoice_status, "s"),
    ("ID wysyłki", lambda r: r.tx.shipment_id, "s"),
    ("ID transakcji", lambda r: r.tx.transaction_id, "s"),
    ("Plik CSV", lambda r: r.tx.source_file, "s"),
    ("Wiersz CSV", lambda r: r.tx.row_number, "s"),
]


def _cols_of_type(columns, kind: str) -> list[int]:
    return [i + 1 for i, c in enumerate(columns) if c[2] == kind]


def build_master_sheet(result: MergeResult, name: str = "Wszystko") -> Sheet:
    header = [c[0] for c in MASTER_COLUMNS]
    rows: list[list[Any]] = [header]
    for r in sorted(result.rows, key=_sort_key):
        rows.append([c[1](r) for c in MASTER_COLUMNS])
    return Sheet(
        name=name,
        rows=rows,
        header_row=1,
        money_cols=_cols_of_type(MASTER_COLUMNS, "m"),
        date_cols=_cols_of_type(MASTER_COLUMNS, "d"),
        pct_cols=_cols_of_type(MASTER_COLUMNS, "p"),
    )


def _sort_key(r: MergedRow):
    return (r.tx.tab_name, r.tx.shipment_date or date.min, r.tx.invoice_number, r.tx.asin)


def _col_letter(idx: int) -> str:
    s = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def build_group_sheets(result: MergeResult) -> list[Sheet]:
    groups: dict[str, list[MergedRow]] = {}
    for r in result.rows:
        groups.setdefault(r.tx.tab_name, []).append(r)
    sheets: list[Sheet] = []
    for tab in sorted(groups):
        rows = sorted(groups[tab], key=_sort_key)
        currencies = sorted({r.tx.currency for r in rows if r.tx.currency and r.tx.currency not in ("EUR", "PLN")})
        country, category = (tab.split(" ", 1) + [""])[:2]
        columns: list[tuple[str, Callable[[MergedRow], Any], str]] = [
            ("Numer faktury VAT", lambda r: r.tx.invoice_number, "s"),
            ("Typ transakcji", lambda r: r.tx.transaction_type_pl, "s"),
            ("Data zamówienia", lambda r: r.tx.order_date, "d"),
            ("Data wysyłki", lambda r: r.tx.shipment_date, "d"),
            ("Imię i nazwisko Kupującego", lambda r: r.buyer_name, "s"),
            ("Ulica", lambda r: r.street, "s"),
            ("Miasto i kod pocztowy", lambda r: r.city_line, "s"),
            ("Kraj dostawy", lambda r: r.tx.ship_to_country, "s"),
            ("ASIN", lambda r: r.tx.asin, "s"),
            ("SKU", lambda r: r.tx.sku, "s"),
            ("Nazwa produktu", lambda r: (r.item.description if r.item else None) or None, "s"),
            ("Ilość", lambda r: r.tx.quantity, "s"),
            ("Kwota netto PLN", lambda r: r.net_pln, "m"),
            ("Kwota VAT PLN", lambda r: r.vat_pln, "m"),
            ("Kwota netto EUR", lambda r: r.net_eur, "m"),
            ("Kwota VAT EUR", lambda r: r.vat_eur, "m"),
        ]
        for cur in currencies:
            columns.append((f"Kwota netto {cur}", (lambda c: lambda r: r.tx.total.net if r.tx.currency == c else None)(cur), "m"))
            columns.append((f"Kwota VAT {cur}", (lambda c: lambda r: r.tx.total.vat if r.tx.currency == c else None)(cur), "m"))
        columns += [
            ("Stawka VAT %", lambda r: r.tx.tax_rate_pct, "p"),
            ("Kurs PLN", lambda r: r.rate.rate if r.rate else None, "s"),
            ("Numer zamówienia", lambda r: r.tx.order_id, "s"),
            ("System sprawozdawczości podatkowej", lambda r: r.tx.scheme or "—", "s"),
            ("NIP nabywcy", lambda r: r.tx.buyer_vat or (r.invoice.buyer_vat_id if r.invoice else None), "s"),
            ("Kraj wysyłki (magazyn)", lambda r: r.tx.ship_from_country, "s"),
            ("Dopasowanie PDF", lambda r: r.match, "s"),
        ]
        title = [L.COUNTRY_PL.get(country, country), category, CATEGORY_DESCRIPTION.get(category, "")]
        header = [c[0] for c in columns]
        data = [[c[1](r) for c in columns] for r in rows]
        first, last = 3, 2 + len(data)
        total_row: list[Any] = ["RAZEM"] + [None] * (len(columns) - 1)
        for ci, c in enumerate(columns, start=1):
            if c[2] == "m" and data:
                letter = _col_letter(ci)
                total_row[ci - 1] = Formula(f"=SUM({letter}{first}:{letter}{last})")
        sheets.append(
            Sheet(
                name=tab,
                rows=[title, header] + data + [total_row],
                header_row=2,
                money_cols=_cols_of_type(columns, "m"),
                date_cols=_cols_of_type(columns, "d"),
                pct_cols=_cols_of_type(columns, "p"),
            )
        )
    return sheets


def build_diagnostics_sheet(result: MergeResult, name: str = "Diagnostyka") -> Sheet:
    rows: list[list[Any]] = [["Kategoria", "Element", "Szczegóły"]]
    rows.append(["Podsumowanie", "Transakcje w CSV", len(result.rows)])
    rows.append(["Podsumowanie", "Dopasowane do PDF", result.matched])
    rows.append(["Podsumowanie", "Bez PDF", result.missing])
    rows.append(["Podsumowanie", "Plików PDF", len(result.invoices)])
    if result.csv_duplicates:
        rows.append(["Podsumowanie", "Pominięte duplikaty wierszy CSV", result.csv_duplicates])
    rp = result.rate_provider
    if rp is not None:
        status = "OK" if rp.nbp_available and rp.failures == 0 else (f"niedostępne ({rp.last_error})" if rp.use_nbp else "wyłączone")
        rows.append(["Podsumowanie", "API NBP", status])
    for r in result.rows:
        if r.invoice is None:
            rows.append(["Brak PDF", r.tx.invoice_number or "(brak numeru)", f"zamówienie {r.tx.order_id}, {r.tx.transaction_type_pl}, {r.tx.total.gross} {r.tx.currency}"])
    for inv in result.unmatched_invoices:
        rows.append(["PDF bez transakcji w CSV", inv.file, f"nr {inv.invoice_number or '?'}, zamówienie {inv.order_number or '?'}"])
    for d in result.duplicate_invoices:
        rows.append(["Zduplikowany PDF", d, ""])
    for a in result.ambiguous:
        rows.append(["Niejednoznaczne dopasowanie po nr zamówienia", a.split(":")[0], a])
    for inv in result.invoices:
        for w in inv.warnings:
            rows.append(["Ostrzeżenie PDF", inv.file, w])
    per_invoice_rows: dict[str, int] = {}
    vat_sum: dict[str, float] = {}
    for r in result.rows:
        k = _inv_key(r.tx)
        per_invoice_rows[k] = per_invoice_rows.get(k, 0) + 1
        vat_sum[k] = round2(vat_sum.get(k, 0.0) + r.tx.total.vat)
    reported: set[str] = set()
    for r in result.rows:
        k = _inv_key(r.tx)
        if r.amount_check.startswith("RÓŻNICA") and k not in reported:
            reported.add(k)
            rows.append(["Kwota PDF ≠ CSV", r.tx.invoice_number, f"{r.amount_check}: PDF {r.invoice.invoice_total} vs CSV {r.tx.total.gross}"])
        if r.amount_check == "BRAK SUMY W PDF":
            rows.append(["Brak sumy w PDF", r.tx.invoice_number, f"plik {r.invoice.file} – nie odczytano kwoty faktury"])
        if r.invoice and r.invoice.currency and r.tx.currency and r.invoice.currency != r.tx.currency:
            rows.append(["Waluta PDF ≠ CSV", r.tx.invoice_number, f"PDF {r.invoice.currency} vs CSV {r.tx.currency}"])
        if r.invoice and r.tx.order_id and r.invoice.order_number and r.invoice.order_number != r.tx.order_id:
            rows.append(["Nr zamówienia PDF ≠ CSV", r.tx.invoice_number, f"PDF {r.invoice.order_number} vs CSV {r.tx.order_id}"])
        if r.rate is None and r.tx.currency != "PLN":
            rows.append(["Brak kursu PLN", r.tx.invoice_number, f"{r.tx.currency}, data bazowa {r.rate_basis_date}"])
        elif r.rate_note.startswith("kurs z daty noty"):
            rows.append(["Kurs noty kredytowej", r.tx.invoice_number, r.rate_note])
        if r.invoice and r.invoice.is_credit_note != r.tx.is_negative:
            rows.append(["Typ dokumentu ≠ typ transakcji", r.tx.invoice_number,
                         f"PDF: {DOC_TYPE_PL.get(r.invoice.doc_type, '?')}, CSV: {r.tx.transaction_type_pl}"])
        if r.invoice and r.invoice.total_vat is not None and abs(abs(r.invoice.total_vat) - abs(vat_sum.get(k, r.tx.total.vat))) > 0.011 \
                and ("vat:" + k) not in reported:
            reported.add("vat:" + k)
            rows.append(["VAT PDF ≠ CSV", r.tx.invoice_number, f"PDF {r.invoice.total_vat} vs CSV {vat_sum.get(k)}"])
    known_numbers = {r.tx.invoice_number for r in result.rows}
    for inv in result.invoices:
        if inv.is_credit_note and inv.original_invoice_number and inv.original_invoice_number not in known_numbers:
            rows.append(["Nota do faktury spoza raportu", inv.invoice_number or inv.file,
                         f"faktura pierwotna {inv.original_invoice_number} nie występuje w CSV (wcześniejszy okres?)"])
    return Sheet(name=name, rows=rows, header_row=1)


def build_sheets(result: MergeResult) -> list[Sheet]:
    return [build_master_sheet(result)] + build_group_sheets(result) + [build_diagnostics_sheet(result)]
