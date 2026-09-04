"""Raport Amazon "VAT Transactions Report" (CSV, ok. 80 kolumn) -> Transaction."""
from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

from . import labels as L

log = logging.getLogger(__name__)

TRANSACTION_TYPE_PL = {
    "SHIPMENT": "Sprzedaż",
    "REFUND": "Zwrot płatności",
    "RETURN": "Zwrot towaru",
    "LIQUIDATION": "Likwidacja",
    "COMMINGLING_BUY": "Commingling – zakup",
    "COMMINGLING_SELL": "Commingling – sprzedaż",
    "FC_TRANSFER": "Transfer FC",
    "INBOUND": "Dostawa do FC",
}

CATEGORY_DESCRIPTION = {
    "OSS": "Sprzedaż B2C do konsumentów w UE rozliczana w procedurze OSS (VAT kraju konsumpcji)",
    "Lokalna": "Sprzedaż z lokalnej rejestracji VAT (VAT kraju rejestracji sprzedawcy)",
    "WDT": "Wewnątrzwspólnotowa dostawa towarów B2B (0%, nabywca z NIP UE, odwrotne obciążenie)",
    "B2B": "Sprzedaż krajowa do nabywcy z NIP (VAT naliczony)",
    "Marketplace": "Amazon jako deemed reseller – VAT pobiera i rozlicza Amazon (np. UK)",
    "Eksport": "Eksport poza UE (0%)",
}

_CSV_DATE_RE = re.compile(r"^(\d{1,2})[-/ .]([A-Za-z]{3,})[-/ .](\d{4})")


def parse_csv_date(value: str | None) -> date | None:
    """'12-Aug-2026 UTC' -> date. Niezależne od locale."""
    s = (value or "").strip()
    if not s:
        return None
    s = re.sub(r"\s*UTC$", "", s)
    m = _CSV_DATE_RE.match(s)
    if m:
        mon = L.MONTHS.get(L.norm(m.group(2)))
        if mon:
            try:
                return date(int(m.group(3)), mon, int(m.group(1)))
            except ValueError:
                return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    from .invoice_pdf import parse_date_text  # późny import (unikamy cyklu)

    return parse_date_text(s)


def to_float(value: str | None) -> float | None:
    s = (value or "").strip().replace(" ", "").replace(" ", "")
    if s in ("", "-", "—"):
        return None
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "," in s and "." in s:
        # 1,234.56 albo 1.234,56 – decyduje ostatni separator
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def to_bool(value: str | None) -> bool | None:
    s = (value or "").strip().lower()
    if s in ("true", "1", "yes", "tak", "y"):
        return True
    if s in ("false", "0", "no", "nie", "n"):
        return False
    return None


@dataclass
class Money:
    net: float = 0.0
    vat: float = 0.0
    gross: float = 0.0

    def __add__(self, other: "Money") -> "Money":
        return Money(round(self.net + other.net, 2), round(self.vat + other.vat, 2), round(self.gross + other.gross, 2))


@dataclass
class Transaction:
    raw: dict = field(default_factory=dict)
    source_file: str = ""
    row_number: int = 0
    marketplace: str = ""
    merchant_id: str = ""
    order_date: date | None = None
    shipment_date: date | None = None
    tax_calculation_date: date | None = None
    transaction_type: str = ""
    is_invoice_corrected: bool | None = None
    order_id: str = ""
    shipment_id: str = ""
    transaction_id: str = ""
    asin: str = ""
    sku: str = ""
    quantity: int | None = None
    tax_rate: float | None = None          # 0.19 -> 19%
    product_tax_code: str = ""
    currency: str = ""
    tax_type: str = ""
    tax_reason: str = ""
    scheme: str = ""                        # Tax Reporting Scheme (VCS_EU_OSS, DEEMED_RESELLER, '')
    collection_responsibility: str = ""     # Seller / Marketplace
    jurisdiction_name: str = ""
    item: Money = field(default_factory=Money)
    shipping: Money = field(default_factory=Money)
    giftwrap: Money = field(default_factory=Money)
    total: Money = field(default_factory=Money)
    seller_vat: str = ""
    seller_jurisdiction: str = ""
    buyer_vat: str = ""
    buyer_vat_jurisdiction: str = ""
    buyer_vat_type: str = ""
    invoice_currency: str = ""
    invoice_exchange_rate: float | None = None
    invoice_exchange_rate_date: date | None = None
    converted_tax_amount: float | None = None
    invoice_number: str = ""
    invoice_url: str = ""
    export_outside_eu: bool | None = None
    ship_from_city: str = ""
    ship_from_state: str = ""
    ship_from_country: str = ""
    ship_from_postal: str = ""
    ship_to_city: str = ""
    ship_to_state: str = ""
    ship_to_country: str = ""
    ship_to_postal: str = ""
    return_fc_country: str = ""
    is_amazon_invoiced: bool | None = None
    original_invoice_number: str = ""
    invoice_correction_details: str = ""
    ksef_number: str = ""
    buyer_nip: str = ""
    seller_nip: str = ""
    einvoice_status: str = ""
    einvoice_url: str = ""
    category: str = ""
    tab_country: str = ""
    tab_name: str = ""

    @property
    def transaction_type_pl(self) -> str:
        return TRANSACTION_TYPE_PL.get(self.transaction_type.upper(), self.transaction_type)

    @property
    def tax_rate_pct(self) -> float | None:
        return None if self.tax_rate is None else round(self.tax_rate * 100, 2)

    @property
    def is_negative(self) -> bool:
        return self.transaction_type.upper() in ("REFUND", "RETURN")


def _money(raw: dict, comp: str) -> Money:
    def f(col: str) -> float:
        return to_float(raw.get(col)) or 0.0

    net = f(f"{comp} Tax Exclusive Selling Price") + f(f"{comp} Tax Exclusive Promo Amount")
    vat = f(f"{comp} Tax Amount") + f(f"{comp} Tax Amount Promo")
    gross = f(f"{comp} Tax Inclusive Selling Price") + f(f"{comp} Tax Inclusive Promo Amount")
    return Money(round(net, 2), round(vat, 2), round(gross, 2))


def classify(tx: Transaction) -> str:
    scheme = (tx.scheme or "").upper()
    resp = (tx.collection_responsibility or "").upper()
    if "OSS" in scheme:
        return "OSS"
    if resp == "MARKETPLACE" or "DEEMED" in scheme:
        return "Marketplace"
    if tx.export_outside_eu:
        return "Eksport"
    if tx.buyer_vat:
        if (tx.tax_rate or 0) == 0 and tx.ship_from_country and tx.ship_from_country != tx.ship_to_country:
            return "WDT"
        return "B2B"
    return "Lokalna"


def tab_country(tx: Transaction) -> str:
    if tx.category == "OSS":
        return tx.ship_to_country or "??"
    return (
        tx.seller_jurisdiction
        or L.JURISDICTION_TO_ISO.get((tx.jurisdiction_name or "").upper(), "")
        or tx.ship_from_country
        or "??"
    )


def transaction_from_row(raw: dict, source_file: str = "", row_number: int = 0) -> Transaction:
    g = lambda col: (raw.get(col) or "").strip()  # noqa: E731
    tx = Transaction(raw=dict(raw), source_file=source_file, row_number=row_number)
    tx.marketplace = g("Marketplace ID")
    tx.merchant_id = g("Merchant ID")
    tx.order_date = parse_csv_date(g("Order Date"))
    tx.shipment_date = parse_csv_date(g("Shipment Date"))
    tx.tax_calculation_date = parse_csv_date(g("Tax Calculation Date"))
    tx.transaction_type = g("Transaction Type").upper()
    tx.is_invoice_corrected = to_bool(g("Is Invoice Corrected"))
    tx.order_id = g("Order ID")
    tx.shipment_id = g("Shipment ID")
    tx.transaction_id = g("Transaction ID")
    tx.asin = g("ASIN")
    tx.sku = g("SKU")
    q = to_float(g("Quantity"))
    tx.quantity = int(q) if q is not None else None
    tx.tax_rate = to_float(g("Tax Rate"))
    tx.product_tax_code = g("Product Tax Code")
    tx.currency = g("Currency").upper()
    tx.tax_type = g("Tax Type")
    tx.tax_reason = g("Tax Calculation Reason Code")
    tx.scheme = g("Tax Reporting Scheme")
    tx.collection_responsibility = g("Tax Collection Responsibility")
    tx.jurisdiction_name = g("Jurisdiction Name")
    tx.item = _money(raw, "OUR_PRICE")
    tx.shipping = _money(raw, "SHIPPING")
    tx.giftwrap = _money(raw, "GIFTWRAP")
    tx.total = tx.item + tx.shipping + tx.giftwrap
    tx.seller_vat = g("Seller Tax Registration")
    tx.seller_jurisdiction = g("Seller Tax Registration Jurisdiction").upper()
    tx.buyer_vat = g("Buyer Tax Registration")
    tx.buyer_vat_jurisdiction = g("Buyer Tax Registration Jurisdiction").upper()
    tx.buyer_vat_type = g("Buyer Tax Registration Type")
    tx.invoice_currency = g("Invoice Level Currency Code").upper()
    rate = to_float(g("Invoice Level Exchange Rate"))
    tx.invoice_exchange_rate = rate if rate else None
    tx.invoice_exchange_rate_date = parse_csv_date(g("Invoice Level Exchange Rate Date"))
    tx.converted_tax_amount = to_float(g("Converted Tax Amount"))
    tx.invoice_number = g("VAT Invoice Number").upper()
    tx.invoice_url = g("Invoice Url")
    tx.export_outside_eu = to_bool(g("Export Outside EU"))
    tx.ship_from_city = g("Ship From City")
    tx.ship_from_state = g("Ship From State")
    tx.ship_from_country = g("Ship From Country").upper()
    tx.ship_from_postal = g("Ship From Postal Code")
    tx.ship_to_city = g("Ship To City")
    tx.ship_to_state = g("Ship To State")
    tx.ship_to_country = g("Ship To Country").upper()
    tx.ship_to_postal = g("Ship To Postal Code")
    tx.return_fc_country = g("Return Fc Country")
    tx.is_amazon_invoiced = to_bool(g("Is Amazon Invoiced"))
    tx.original_invoice_number = g("Original VAT Invoice Number").upper()
    tx.invoice_correction_details = g("Invoice Correction Details")
    tx.ksef_number = g("KSeF Number")
    tx.buyer_nip = g("Buyer NIP")
    tx.seller_nip = g("Seller NIP")
    tx.einvoice_status = g("E-Invoice Delivery Status")
    tx.einvoice_url = g("EInvoice URL")
    tx.category = classify(tx)
    tx.tab_country = tab_country(tx)
    tx.tab_name = f"{tx.tab_country} {tx.category}"
    return tx


REQUIRED_COLUMNS = ("Order ID", "Transaction Type", "VAT Invoice Number", "Currency")


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        return ","


def read_report(path: str | Path) -> list[Transaction]:
    path = Path(path)
    raw_bytes = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
        try:
            text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover
        text = raw_bytes.decode("utf-8", errors="replace")
    delimiter = _sniff_delimiter(text[:5000])
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    fields = [f.strip() for f in (reader.fieldnames or [])]
    reader.fieldnames = fields
    missing = [c for c in REQUIRED_COLUMNS if c not in fields]
    if missing:
        raise ValueError(f"{path.name}: to nie wygląda na raport VAT Transactions – brak kolumn {missing}")
    out: list[Transaction] = []
    for i, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        out.append(transaction_from_row(row, path.name, i))
    log.info("CSV %s: %d transakcji", path.name, len(out))
    return out


def read_reports(paths: Iterable[str | Path], stats: dict | None = None) -> list[Transaction]:
    """Wczytuje kilka raportów; identyczne wiersze (np. ten sam plik podany dwa razy) są pomijane.

    `stats` (opcjonalny słownik) dostaje liczbę pominiętych duplikatów pod kluczem 'duplicates'.
    """
    out: list[Transaction] = []
    seen: set[tuple] = set()
    dups = 0
    for p in paths:
        for tx in read_report(p):
            key = (tx.invoice_number, tx.order_id, tx.asin, tx.transaction_type, tx.transaction_id,
                   tx.shipment_id, tx.shipment_date, tx.quantity, tx.total.gross)
            if key in seen:
                dups += 1
                continue
            seen.add(key)
            out.append(tx)
    if dups:
        log.warning("pominięto %d zduplikowanych wierszy CSV (identyczne faktura/zamówienie/ASIN/wysyłka/kwota)", dups)
    if stats is not None:
        stats["duplicates"] = dups
    return out
