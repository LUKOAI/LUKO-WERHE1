"""Parser faktur Amazon VCS (PDF) oparty na współrzędnych słów (pdfplumber).

Układ faktury Amazon jest stały niezależnie od języka:
  * prawy górny blok: tytuł, status, referencja płatności, sprzedawca, NIP,
    data faktury, nr faktury, (nr faktury pierwotnej), razem do zapłaty
  * lewy górny blok: adres nabywcy (WIELKIMI LITERAMI)
  * blok 3 kolumn: adres rozliczeniowy | adres dostawy | sprzedawca
  * sekcja zamówienia: data zamówienia, nr zamówienia
  * tabela pozycji (opis / ilość / cena / stawka / suma) z liniami "ASIN: ..."
  * koszty wysyłki, rabat, suma faktury, podsumowanie VAT, przeliczenie na walutę
    rejestracji (np. "CZK0.00"), przypisy, kraj wysyłki.
Parser nie rzuca wyjątków na nieznanym układzie – brakujące pola zostają None,
a problemy trafiają do `Invoice.warnings`.
"""
from __future__ import annotations

import logging
import re
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

from . import labels as L

log = logging.getLogger(__name__)

INVOICE_NO_RE = re.compile(r"(?<![0-9A-Z])[A-Z]{2}[0-9A-Z]{12}(?![0-9A-Z])")
NON_INVOICE_TOKEN_RE = re.compile(r"^(NL\d{9}B\d{2}|GB\d{12})$")
ORDER_NO_RE = re.compile(r"\b\d{3}-\d{7}-\d{7}\b")
VAT_ID_RE = re.compile(r"\b[A-Z]{2}[0-9A-Z]{8,13}\b")
ASIN_RE = re.compile(r"\b(B0[0-9A-Z]{8}|\d{9}[0-9X])\b")
COUNTRY_LINE_RE = re.compile(r"^[A-Z]{2}$")
RATE_RE = re.compile(r"^(\d{1,2}(?:[.,]\d{1,2})?)\s?%$")
CONVERSION_RE = re.compile(r"^([A-Z]{3})\s?([-−–]?\d[\d.,\s]*)$")
_AMOUNT_CORE = r"\d{1,3}(?:[  .,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_CUR = r"[€£$]|zł|kr|kč|[A-Z]{3}"
AMOUNT_TOKEN_RE = re.compile(
    r"^(?P<sign>[-−–])?\s?(?P<pre>" + _CUR + r")?\s?(?P<sign2>[-−–])?\s?(?P<num>" + _AMOUNT_CORE
    + r")\s?(?P<post>" + _CUR + r")?$",
    re.IGNORECASE,
)
_VAT_LABEL = (
    r"(?:nip|p\.? ?iva|partita iva|tva|ust-?idnr\.?|ust-?id|iva|nif|cif|btw(?:-nummer|-id)?|"
    r"vat(?: no\.?| number| id| #)?|momsreg\.? ?nr|dič|steuernummer)"
)
STREET_VAT_RE = re.compile(r",?\s*" + _VAT_LABEL + r"\s*:?\s*#?\s*([A-Z]{2}[0-9A-Z]{8,13})\s*$", re.IGNORECASE)
VAT_LINE_RE = re.compile(r"^" + _VAT_LABEL + r"\s*:?\s*#?\s*([A-Z]{2}[0-9A-Z]{8,13})\s*$", re.IGNORECASE)
DATE_RES = [
    re.compile(r"(\d{1,2})\.?\s*(?:de\s+)?([^\d\s,.]+)\.?,?\s*(?:de\s+)?(\d{4})"),
    re.compile(r"([^\d\s,.]+)\.?\s+(\d{1,2}),?\s+(\d{4})"),
    re.compile(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})"),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
]

BUYER_HEADER_LABELS = [
    "adres nabywcy", "dane nabywcy", "indirizzo dell'acquirente", "indirizzo acquirente",
    "adresse de l'acheteur", "käuferadresse", "adresse des käufers", "anschrift des käufers",
    "dirección del comprador", "direccion del comprador", "adres koper", "adres van de koper",
    "köparens adress", "buyer address", "bill to", "rechnung an", "facturer à",
]


# ---------------------------------------------------------------------------
# struktury danych
# ---------------------------------------------------------------------------
@dataclass
class Address:
    name: str | None = None
    street: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None
    country_name: str | None = None
    vat_id: str | None = None
    city_line: str | None = None
    lines: list[str] = field(default_factory=list)
    street_lines: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.lines


@dataclass
class InvoiceItem:
    description: str | None = None
    asin: str | None = None
    quantity: int | None = None
    unit_price_net: float | None = None
    vat_rate: float | None = None
    unit_price_gross: float | None = None
    line_total: float | None = None
    raw_lines: list[str] = field(default_factory=list)


@dataclass
class VatLine:
    rate: float | None
    net: float | None
    vat: float | None


@dataclass
class Invoice:
    file: str
    invoice_number: str | None = None
    invoice_number_source: str | None = None
    original_invoice_number: str | None = None
    doc_type: str = "unknown"          # invoice | credit_note | unknown
    title: str | None = None
    language: str = "unknown"
    pages: int = 0
    paid: bool | None = None
    payment_status: str | None = None  # paid | refunded | due
    payment_reference: str | None = None
    customer_number: str | None = None
    seller_name: str | None = None
    seller_vat_id: str | None = None
    invoice_date: date | None = None
    delivery_date: date | None = None
    order_date: date | None = None
    order_number: str | None = None
    total_to_pay: float | None = None
    invoice_total: float | None = None
    shipping_gross: float | None = None
    discount_gross: float | None = None
    currency: str | None = None
    billing: Address = field(default_factory=Address)
    shipping: Address = field(default_factory=Address)
    seller: Address = field(default_factory=Address)
    buyer_header: Address = field(default_factory=Address)
    items: list[InvoiceItem] = field(default_factory=list)
    vat_lines: list[VatLine] = field(default_factory=list)
    total_net: float | None = None
    total_vat: float | None = None
    converted_vat_currency: str | None = None
    converted_vat_amount: float | None = None
    exchange_rate: float | None = None
    shipped_from: str | None = None
    shipped_from_country: str | None = None
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    text: str = ""

    # --- wygodne aliasy używane przez merge ---
    @property
    def buyer_name(self) -> str | None:
        return self.billing.name or self.buyer_header.name or self.shipping.name

    @property
    def buyer_vat_id(self) -> str | None:
        return self.billing.vat_id or self.buyer_header.vat_id or self.shipping.vat_id

    @property
    def is_credit_note(self) -> bool:
        return self.doc_type == "credit_note"

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("invoice_date", "order_date", "delivery_date"):
            if d[k] is not None:
                d[k] = d[k].isoformat()
        d.pop("text", None)
        return d


# ---------------------------------------------------------------------------
# pomocnicze: kwoty, daty
# ---------------------------------------------------------------------------
def parse_amount(token: str) -> float | None:
    """'121,87' / '1.234,56' / '12.90' / '-3,99' / '1 234,56' -> float."""
    if token is None:
        return None
    s = str(token).strip().replace(" ", " ").replace(" ", "")
    if not s:
        return None
    neg = s[0] in "-−–"
    s = s.lstrip("-−–")
    if not re.fullmatch(r"\d[\d.,]*", s):
        return None
    int_part, frac = s, "00"
    m_dec = re.fullmatch(r"(\d+)[.,](\d{3,})", s)
    if m_dec and "," in s and "." not in s and len(m_dec.group(2)) != 3:
        # '4,2345' (kurs) – jeden przecinek i więcej niż 3 cyfry po nim to część dziesiętna
        return float(f"{m_dec.group(1)}.{m_dec.group(2)}") * (-1 if neg else 1)
    if len(s) >= 3 and s[-3] in ",." and s[-2:].isdigit():
        int_part, frac = s[:-3], s[-2:]
    elif len(s) >= 2 and s[-2] in ",." and s[-1].isdigit():
        int_part, frac = s[:-2], s[-1] + "0"
    int_part = re.sub(r"[.,]", "", int_part)
    if not int_part:
        int_part = "0"
    try:
        val = float(f"{int_part}.{frac}")
    except ValueError:
        return None
    return -val if neg else val


def amount_token(token: str) -> tuple[float, str | None] | None:
    """Rozpoznaje token kwoty (z opcjonalnym symbolem waluty i znakiem) -> (kwota, waluta)."""
    m = AMOUNT_TOKEN_RE.match(token.strip())
    if not m:
        return None
    num = m.group("num")
    has_cur = bool(m.group("pre") or m.group("post"))
    # sam integer bez separatora dziesiętnego i bez symbolu waluty to nie kwota
    if not re.search(r"[.,]\d{1,2}$", num) and not has_cur:
        return None
    val = parse_amount(num)
    if val is None:
        return None
    if m.group("sign") or m.group("sign2"):
        val = -abs(val)
    sym = (m.group("pre") or m.group("post") or "").strip()
    if len(sym) == 3 and sym.upper() not in L.CURRENCY_CODES and sym.lower() not in L.CURRENCY_SYMBOLS:
        return None   # 'von 30', 'Art 194' – trzyliterowe słowo to nie kod waluty
    cur = L.CURRENCY_SYMBOLS.get(sym.lower()) or (sym.upper() if len(sym) == 3 else None)
    return val, cur


def parse_date_text(text: str) -> date | None:
    if not text:
        return None
    t = text.strip()
    for i, rx in enumerate(DATE_RES):
        for m in rx.finditer(t):
            try:
                if i == 0:
                    d, mon, y = int(m.group(1)), L.MONTHS.get(L.norm(m.group(2))), int(m.group(3))
                elif i == 1:
                    mon, d, y = L.MONTHS.get(L.norm(m.group(1))), int(m.group(2)), int(m.group(3))
                elif i == 2:
                    d, mon, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                else:
                    y, mon, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if mon and 1 <= mon <= 12 and 1 <= d <= 31 and 1900 < y < 2200:
                    return date(y, mon, d)
            except (ValueError, TypeError):
                continue
    return None


# ---------------------------------------------------------------------------
# linie z pdfplumber
# ---------------------------------------------------------------------------
@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float


@dataclass
class Line:
    top: float
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def x0(self) -> float:
        return self.words[0].x0 if self.words else 0.0


def _build_lines(words: Iterable[Word], tol: float = 3.0) -> list[Line]:
    ws = sorted(words, key=lambda w: (w.top, w.x0))
    lines: list[Line] = []
    for w in ws:
        if lines and abs(lines[-1].top - w.top) <= tol:
            lines[-1].words.append(w)
        else:
            lines.append(Line(top=w.top, words=[w]))
    for ln in lines:
        ln.words.sort(key=lambda w: w.x0)
    return lines


def _extract_words(path: Path) -> tuple[list[Word], float, float, str, int]:
    import pdfplumber  # import lokalny – ciężka zależność

    words: list[Word] = []
    texts: list[str] = []
    width = height = 0.0
    npages = 0
    with pdfplumber.open(str(path)) as pdf:
        for pno, page in enumerate(pdf.pages):
            npages += 1
            width, height = float(page.width), float(page.height)
            offset = pno * (height + 50)
            for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
                words.append(Word(w["text"], float(w["x0"]), float(w["x1"]), float(w["top"]) + offset))
            texts.append(page.extract_text() or "")
    return words, width, height, "\n".join(texts), npages


def _first_label_line(lines: list[Line], key: str) -> int | None:
    for i, ln in enumerate(lines):
        if L.match_label(ln.text, key) is not None:
            return i
    return None


def _line_contains_label(text: str, key: str) -> bool:
    t = L.norm(text)
    return any(lbl in t for lbl in L.NORM_LABELS[key])


def _is_any_label(text: str) -> bool:
    return any(L.match_label(text, k) is not None for k in L.LABELS)


# ---------------------------------------------------------------------------
# adresy
# ---------------------------------------------------------------------------
def parse_address(lines: list[str]) -> Address:
    lines = [ln.strip() for ln in lines if ln and ln.strip()]
    addr = Address(lines=list(lines))
    if not lines:
        return addr
    addr.name = lines[0]
    rest: list[str] = []
    for ln in lines[1:]:
        m = VAT_LINE_RE.match(ln)
        if m:
            addr.vat_id = addr.vat_id or m.group(1)
            continue
        rest.append(ln)
    # linia kraju: kod ISO albo nazwa słowna (np. "Luxemburg")
    if rest:
        last = rest[-1]
        iso = L.country_to_iso(last) if (COUNTRY_LINE_RE.match(last) or not re.search(r"\d", last)) else None
        if iso:
            addr.country = iso
            addr.country_name = last
            rest = rest[:-1]
    if rest:
        addr.city_line = rest[-1]
        street_lines = []
        for ln in rest[:-1]:
            m = STREET_VAT_RE.search(ln)
            if m:
                addr.vat_id = addr.vat_id or m.group(1)
                ln = ln[: m.start()].rstrip(" ,")
            if ln:
                street_lines.append(ln)
        addr.street_lines = street_lines
        addr.street = ", ".join(street_lines) if street_lines else None
        parts = [p.strip() for p in addr.city_line.split(",") if p.strip()]
        if parts:
            addr.city = parts[0]
            postal = None
            for p in reversed(parts[1:]):
                if re.search(r"\d", p) and len(p) <= 12:
                    postal = p
                    break
            if postal is None and len(parts) == 1:
                # "Homburg 66424" bez przecinka, albo sam kod "L-1855"
                m = re.match(r"^(.*?)[\s,]+([A-Z0-9][A-Z0-9 -]{2,9})$", parts[0])
                if m and re.search(r"\d", m.group(2)):
                    addr.city, postal = m.group(1).strip(), m.group(2)
                elif re.fullmatch(r"[A-Z]{0,2}-?\d[\d -]{2,9}", parts[0]):
                    addr.city, postal = None, parts[0]
            addr.postal_code = postal
            region_parts = [p for p in parts[1:] if p != postal]
            addr.region = ", ".join(region_parts) if region_parts else None
    return addr


def _split_columns(header: Line, gap: float = 25.0) -> list[float]:
    """Punkty x początku kolumn w linii nagłówka bloku adresów (po dużych odstępach)."""
    starts = [header.words[0].x0]
    for prev, cur in zip(header.words, header.words[1:]):
        if cur.x0 - prev.x1 > gap:
            starts.append(cur.x0)
    return starts


def _assign_column(x0: float, starts: list[float]) -> int:
    idx = 0
    for i, s in enumerate(starts):
        if x0 >= s - 4:
            idx = i
    return idx


def _is_address_header(text: str) -> bool:
    return _line_contains_label(text, "billing_address") or _line_contains_label(text, "shipping_address")


def _parse_address_block(body: list[Line], inv: Invoice) -> None:
    hi = None
    for i, ln in enumerate(body):
        if _is_address_header(ln.text):
            hi = i
            break
    if hi is None:
        inv.warnings.append("brak nagłówka bloku adresów (adres rozliczeniowy / dostawy)")
        return
    header = body[hi]
    starts = _split_columns(header)
    roles: list[str] = []
    for k, s in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else 1e9
        txt = " ".join(w.text for w in header.words if s - 4 <= w.x0 < end - 4)
        if _line_contains_label(txt, "billing_address"):
            roles.append("billing")
        elif _line_contains_label(txt, "shipping_address"):
            roles.append("shipping")
        elif L.match_label(txt, "seller") is not None:
            roles.append("seller")
        else:
            roles.append(["billing", "shipping", "seller"][k] if k < 3 else f"col{k}")
    cols: dict[str, list[str]] = {r: [] for r in roles}
    prev_top = header.top
    gaps: list[float] = []
    for ln in body[hi + 1:]:
        gap = ln.top - prev_top
        typical = statistics.median(gaps) if gaps else gap
        if gaps and gap > max(22.0, typical * 1.7):
            break
        if L.match_label(ln.text, "order_details") is not None or L.match_label(ln.text, "items_header") is not None:
            break
        if ln.x0 < starts[0] - 12:
            break
        buckets: dict[int, list[str]] = {}
        for w in ln.words:
            buckets.setdefault(_assign_column(w.x0, starts), []).append(w.text)
        for k, texts in buckets.items():
            role = roles[k] if k < len(roles) else f"col{k}"
            cols.setdefault(role, []).append(" ".join(texts))
        gaps.append(gap)
        prev_top = ln.top
    inv.billing = parse_address(cols.get("billing", []))
    inv.shipping = parse_address(cols.get("shipping", []))
    inv.seller = parse_address(cols.get("seller", []))
    _fix_wrapped_name(inv.billing, inv.buyer_header)
    if inv.billing.empty:
        inv.warnings.append("pusty adres rozliczeniowy")


def _squash(text: str) -> str:
    return re.sub(r"[\s,.]+", "", (text or "")).upper()


def _fix_wrapped_name(addr: Address, header: Address) -> None:
    """Kolumna adresowa ma ~40 znaków szerokości – długa nazwa firmy łamie się na 2 linie
    i druga linia ląduje w ulicy. Blok nagłówka (WIELKIMI LITERAMI) jest szerszy, więc gdy jego
    pierwsza linia == nazwa + pierwsza linia ulicy, sklejamy nazwę i skracamy ulicę."""
    if not addr.name or not addr.street_lines or not header.name:
        return
    joined = ""
    for k in range(1, len(addr.street_lines)):
        joined = f"{addr.name} {' '.join(addr.street_lines[:k])}"
        if _squash(joined) == _squash(header.name) and _squash(header.name) != _squash(addr.name):
            addr.name = joined
            addr.street_lines = addr.street_lines[k:]
            addr.street = ", ".join(addr.street_lines) if addr.street_lines else None
            return


# ---------------------------------------------------------------------------
# nagłówek (prawa / lewa kolumna)
# ---------------------------------------------------------------------------
def _kv_all(lines: list[Line], key: str) -> list[str]:
    """Wszystkie wartości dla etykiety `key` (wartość z tej samej lub następnej linii)."""
    out: list[str] = []
    for i, ln in enumerate(lines):
        v = L.match_label(ln.text, key)
        if v is None:
            continue
        if v:
            out.append(v)
        elif i + 1 < len(lines) and not _is_any_label(lines[i + 1].text):
            out.append(lines[i + 1].text.strip())
        else:
            out.append("")
    return out


def _kv_first(lines: list[Line], key: str) -> str | None:
    vals = _kv_all(lines, key)
    return vals[0] if vals else None


def _amounts_in(text: str) -> tuple[list[float], str | None]:
    words = [Word(t, 0.0, 0.0, 0.0) for t in text.split()]
    nums = _numbers_from_words(words)
    return nums["amounts"], nums["currency"]


def _parse_header(right: list[Line], left: list[Line], inv: Invoice, stem_number: str | None) -> None:
    titles = [ln.text.strip() for ln in right if ln.top < 60]
    if titles:
        inv.title = " / ".join(titles)
        credit = {L.norm(t) for t in L.DOC_TITLES_CREDIT}
        invoice = {L.norm(t) for t in L.DOC_TITLES_INVOICE}
        for t in titles:
            nt = L.norm(t)
            if nt in credit:
                inv.doc_type = "credit_note"
                break
            if nt in invoice and inv.doc_type == "unknown":
                inv.doc_type = "invoice"
    for ln in right:
        nt = L.norm(ln.text)
        if nt in L.NORM_LABELS["paid"]:
            inv.paid, inv.payment_status = True, "paid"
        elif nt in L.NORM_LABELS["refunded"]:
            inv.paid, inv.payment_status = None, "refunded"
        elif L.match_label(ln.text, "payment_due") is not None and inv.payment_status is None:
            inv.payment_status = "due"
        if L.match_label(ln.text, "credit_intro") is not None:
            inv.doc_type = "credit_note"
    v = _kv_first(right, "payment_reference")
    if v:
        inv.payment_reference = re.sub(r"^(id|nr|no\.?|#)\s*[:#]?\s*", "", v, flags=re.IGNORECASE).strip() or None
    inv.customer_number = _kv_first(right, "customer_number") or None
    inv.seller_name = _kv_first(right, "seller") or None
    v = _kv_first(right, "vat_id")
    if v:
        m = VAT_ID_RE.search(v)
        inv.seller_vat_id = m.group(0) if m else v
    for v in _kv_all(right, "invoice_date"):
        d = parse_date_text(v)
        if d:
            inv.invoice_date = d
            break
    v = _kv_first(right, "delivery_date")
    if v:
        inv.delivery_date = parse_date_text(v)
    # numer faktury: wszystkie dopasowania; zdanie "Gutschrift für die Rechnungsnummer X"
    # daje numer faktury pierwotnej, właściwy numer jest w liście klucz/wartość niżej
    cands: list[str] = []
    prev_intro_without_number = False
    for ln in right:
        text = ln.text
        is_original = L.match_label(text, "original_invoice_number") is not None
        is_intro = L.match_label(text, "credit_intro") is not None
        if is_intro:
            # "Dies ist eine Gutschrift ... für die" + w następnej linii "Rechnungsnummer X"
            prev_intro_without_number = INVOICE_NO_RE.search(text.upper()) is None
            continue
        skip_wrapped = prev_intro_without_number
        prev_intro_without_number = False
        if is_original or skip_wrapped:
            continue
        v = L.match_label(text, "invoice_number")
        if v is None:
            continue
        m = INVOICE_NO_RE.search(v.upper())
        if m and m.group(0) not in cands:
            cands.append(m.group(0))
    if cands:
        inv.invoice_number = stem_number if (stem_number and stem_number in cands) else cands[0]
        inv.invoice_number_source = "etykieta"
    v = _kv_first(right, "original_invoice_number")
    if v:
        m = INVOICE_NO_RE.search(v.upper())
        inv.original_invoice_number = m.group(0) if m else v
    if not inv.original_invoice_number:
        for v in _kv_all(right, "credit_intro"):
            m = INVOICE_NO_RE.search(v.upper())
            if m:
                inv.original_invoice_number = m.group(0)
                break
    if not inv.original_invoice_number and len(cands) > 1:
        inv.original_invoice_number = next((c for c in cands if c != inv.invoice_number), None)
    if inv.original_invoice_number and inv.original_invoice_number == inv.invoice_number:
        inv.original_invoice_number = None
    if inv.original_invoice_number and inv.doc_type == "unknown":
        inv.doc_type = "credit_note"
    v = _kv_first(right, "total_to_pay")
    if v:
        amounts, cur = _amounts_in(v)
        if amounts:
            inv.total_to_pay = amounts[-1]
            inv.currency = inv.currency or cur
    # lewy blok = adres nabywcy WIELKIMI LITERAMI
    left_texts = [ln.text for ln in left]
    if left_texts and L.norm(left_texts[0]) in {L.norm(b) for b in BUYER_HEADER_LABELS}:
        left_texts = left_texts[1:]
    left_texts = [t for t in left_texts if not L.is_boilerplate(t)]
    inv.buyer_header = parse_address(left_texts)


# ---------------------------------------------------------------------------
# pozycje, sumy
# ---------------------------------------------------------------------------
def _find_qty_x(body: list[Line], start: int) -> float | None:
    for ln in body[start: start + 4]:
        for w in ln.words:
            if L.norm(w.text) in L.NORM_LABELS["qty"]:
                return w.x0
    return None


def _merge_thousands(words: list[Word]) -> list[Word]:
    """'1 234,56' rozbite przez pdfplumber na '1' i '234,56' (odstęp ~1 spacji) -> '1234,56'.
    Ilość w osobnej kolumnie ma odstęp kilkudziesięciu punktów, więc nie zostanie sklejona."""
    out: list[Word] = []
    i = 0
    while i < len(words):
        w = words[i]
        if (i + 1 < len(words) and re.fullmatch(r"[-−–]?\d{1,3}", w.text)
                and re.fullmatch(r"\d{3}(?:[  ]\d{3})*(?:[.,]\d{1,2})?", words[i + 1].text)
                and 0 <= words[i + 1].x0 - w.x1 <= 6.0):
            merged = Word(w.text + words[i + 1].text, w.x0, words[i + 1].x1, w.top)
            j = i + 2
            while j < len(words) and re.fullmatch(r"\d{3}(?:[.,]\d{1,2})?", words[j].text) and 0 <= words[j].x0 - merged.x1 <= 6.0:
                merged = Word(merged.text + words[j].text, merged.x0, words[j].x1, merged.top)
                j += 1
            out.append(merged)
            i = j
            continue
        out.append(w)
        i += 1
    return out


def _numbers_from_words(words: list[Word]) -> dict:
    out: dict = {"qty": None, "rate": None, "amounts": [], "currency": None}
    words = _merge_thousands(list(words))
    toks = [w.text for w in words]
    i = 0
    while i < len(toks):
        t = toks[i]
        # "20 %" rozbite na dwa tokeny
        if i + 1 < len(toks) and toks[i + 1] == "%" and re.fullmatch(r"\d{1,2}(?:[.,]\d{1,2})?", t):
            out["rate"] = parse_amount(t)
            i += 2
            continue
        m = RATE_RE.match(t)
        if m:
            out["rate"] = parse_amount(m.group(1))
            i += 1
            continue
        if re.fullmatch(r"\d{1,4}", t) and out["qty"] is None and not out["amounts"]:
            out["qty"] = int(t)
            i += 1
            continue
        # kwota + osobny symbol waluty ("12,90 €" / "€ 12,90" / "-11,76 €")
        joined, consumed = t, 1
        if i + 1 < len(toks) and toks[i + 1].lower() in L.CURRENCY_SYMBOLS:
            joined, consumed = t + toks[i + 1], 2
        a = amount_token(joined)
        if a is None and i + 1 < len(toks):
            a2 = amount_token(t + toks[i + 1])
            if a2:
                a, consumed = a2, 2
        if a:
            out["amounts"].append(a[0])
            out["currency"] = out["currency"] or a[1]
        i += consumed
    return out


def _parse_items(body: list[Line], inv: Invoice) -> int:
    """Zwraca indeks linii, na której skończyła się tabela pozycji (lub len(body))."""
    hi = _first_label_line(body, "items_header")
    if hi is None:
        inv.warnings.append("brak nagłówka tabeli pozycji")
        return 0
    qty_x = _find_qty_x(body, hi + 1)
    if qty_x is None:
        inv.warnings.append("nie znaleziono kolumny ilości – opisy pozycji mogą zawierać liczby")
        qty_x = 300.0
    header_words = {L.norm(x) for k in ("qty", "description") for x in L.NORM_LABELS[k]}
    block: list[Line] = []
    end = len(body)

    def finalize(blk: list[Line], asin: str | None) -> None:
        if not blk and not asin:
            return
        item = InvoiceItem(asin=asin, raw_lines=[b.text for b in blk])
        desc_parts: list[str] = []
        numeric_done = False
        for b in blk:
            left_words = [w.text for w in b.words if w.x0 < qty_x - 5]
            right_words = [w for w in b.words if w.x0 >= qty_x - 5]
            if right_words and not numeric_done:
                nums = _numbers_from_words(right_words)
                item.quantity = nums["qty"]
                item.vat_rate = nums["rate"]
                am = nums["amounts"]
                if am:
                    item.line_total = am[-1]
                    item.unit_price_net = am[0] if len(am) >= 2 else None
                    item.unit_price_gross = am[-2] if len(am) >= 3 else None
                    inv.currency = inv.currency or nums["currency"]
                numeric_done = True
            txt = " ".join(left_words).strip()
            if txt and L.norm(txt) not in header_words:
                desc_parts.append(txt)
        desc = " ".join(desc_parts)
        for noise in L.DESCRIPTION_NOISE:
            desc = re.sub(re.escape(noise), "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\s*\|\s*[A-Z0-9]{10}\s*$", "", desc)   # "... | B07N7CJMNH" (EN)
        desc = re.sub(r"\s+", " ", desc).strip(" ,")
        item.description = desc or None
        inv.items.append(item)

    doc_titles = {L.norm(t) for t in L.DOC_TITLES_INVOICE + L.DOC_TITLES_CREDIT}
    i = hi + 1
    while i < len(body):
        ln = body[i]
        # stopka strony / nagłówek kolejnej strony ("Rechnung", "Rechnungsnummer X", "Seite 1 von 2")
        if L.is_boilerplate(ln.text) or L.norm(ln.text) in doc_titles or (
            L.match_label(ln.text, "invoice_number") is not None and ln.x0 > qty_x
        ):
            i += 1
            continue
        has_left = any(w.x0 < qty_x - 5 for w in ln.words)
        has_digit = any(re.search(r"\d", w.text) for w in ln.words)
        for key in ("shipping", "discount", "invoice_total"):
            if L.match_label(ln.text, key) is not None:
                end = i
                break
        if end == i:
            break
        # sumy / podsumowanie VAT: linia bez tekstu w kolumnie opisu, gdy pozycje już są
        if not block and inv.items and not has_left:
            end = i
            break
        if not block and inv.items and L.match_label(ln.text, "summary_total") is not None:
            end = i
            break
        # nagłówek tabeli (etykiety kolumn, nawiasy): bez cyfr albo słowa nagłówka
        if not block and (not has_digit or any(L.norm(w.text) in header_words for w in ln.words)) \
                and not ASIN_RE.search(ln.text):
            i += 1
            continue
        m = re.search(r"asin\s*:?\s*([A-Z0-9]{10})", ln.text, re.IGNORECASE)
        if m:
            finalize(block, m.group(1).upper())
            block = []
            i += 1
            continue
        # nowa pozycja bez linii ASIN: linia z ilością/kwotą gdy blok już ma liczby
        has_numbers = any(w.x0 >= qty_x - 5 for w in ln.words)
        if block and has_numbers and any(any(w.x0 >= qty_x - 5 for w in b.words) for b in block):
            finalize(block, None)
            block = []
        block.append(ln)
        i += 1
    if block:
        finalize(block, None)
    return end


def _parse_totals(body: list[Line], start: int, inv: Invoice) -> None:
    in_summary = False
    after_summary = False
    for ln in body[start:]:
        text = ln.text
        nums = _numbers_from_words(ln.words)
        am = nums["amounts"]
        if L.is_boilerplate(text):
            continue
        if L.match_label(text, "shipping") is not None and am:
            inv.shipping_gross = am[-1]
            continue
        if L.match_label(text, "discount") is not None and am:
            inv.discount_gross = am[-1]
            continue
        if L.match_label(text, "invoice_total") is not None and am:
            inv.invoice_total = am[-1]
            inv.currency = inv.currency or nums["currency"]
            continue
        if not in_summary and L.match_label(text, "summary_total") is not None and len(am) == 1 and ln.x0 > 250:
            # np. hiszpańskie "Total 19,99 €" jako suma faktury
            inv.invoice_total = am[-1]
            inv.currency = inv.currency or nums["currency"]
            continue
        if L.match_label(text, "total_to_pay") is not None and am and inv.invoice_total is None:
            inv.invoice_total = am[-1]
            continue
        if _line_contains_label(text, "vat_summary_header"):
            in_summary = True
            continue
        m = CONVERSION_RE.match(text.replace(" ", "")) or (
            len(ln.words) <= 2 and CONVERSION_RE.match("".join(w.text for w in ln.words))
        )
        if m:
            inv.converted_vat_currency = m.group(1)
            inv.converted_vat_amount = parse_amount(m.group(2))
            continue
        v = L.match_label(text, "shipped_from")
        if v is not None:
            val = v.lstrip(": ").strip() or None
            if val and not inv.shipped_from:
                inv.shipped_from = val
                inv.shipped_from_country = L.country_to_iso(val)
            continue
        v = L.match_label(text, "exchange_rate")
        if v is not None:
            m2 = re.search(r"\d+[.,]\d+", v)
            if m2:
                inv.exchange_rate = float(m2.group(0).replace(",", "."))
            continue
        if in_summary:
            first = ln.words[0].text if ln.words else ""
            starts_with_rate = bool(RATE_RE.match(first)) or (
                len(ln.words) > 1 and ln.words[1].text == "%" and re.fullmatch(r"\d{1,2}(?:[.,]\d{1,2})?", first)
            )
            if starts_with_rate and nums["rate"] is not None and len(am) == 2:
                inv.vat_lines.append(VatLine(nums["rate"], am[0], am[1]))
                continue
            if L.match_label(text, "summary_total") is not None and am:
                inv.total_net = am[0]
                inv.total_vat = am[1] if len(am) > 1 else None
                after_summary = True
                in_summary = False
                continue
        if after_summary and am and not re.match(r"^\(\d+\)", text.strip()):
            # po podsumowaniu VAT nie ma już kwot do odczytu (np. nagłówek kolejnej strony)
            continue
        if re.match(r"^\(\d+\)", text.strip()) and not am:
            inv.notes.append(text.strip())
            continue
        if (after_summary or in_summary) and ln.x0 < 100 and not am and len(text) > 15:
            inv.notes.append(text.strip())
    if inv.total_net is None and inv.vat_lines:
        inv.total_net = round(sum(v.net or 0 for v in inv.vat_lines), 2)
        inv.total_vat = round(sum(v.vat or 0 for v in inv.vat_lines), 2)


# ---------------------------------------------------------------------------
# główna funkcja
# ---------------------------------------------------------------------------
def parse_pdf(path: str | Path, known_invoice_numbers: Iterable[str] | None = None) -> Invoice:
    path = Path(path)
    inv = Invoice(file=path.name)
    known = {k.upper() for k in (known_invoice_numbers or [])}
    stem_m = INVOICE_NO_RE.search(path.stem.upper())
    stem_number = stem_m.group(0) if stem_m else None
    try:
        words, width, height, text, npages = _extract_words(path)
    except Exception as exc:  # noqa: BLE001 – każdy błąd odczytu ma być raportowany, nie rzucany
        inv.warnings.append(f"nie udało się odczytać PDF: {exc}")
        return inv
    inv.text = text
    inv.pages = npages
    inv.language = L.detect_language(text)
    if not words:
        inv.warnings.append("PDF nie zawiera tekstu (skan?) – wymagane OCR")
        return inv
    all_lines = _build_lines(words)

    # koniec nagłówka: linia z nagłówkiem bloku adresów albo boilerplate 'contact-us'
    header_end = None
    for ln in all_lines:
        if _is_address_header(ln.text):
            header_end = ln.top
            break
    if header_end is None:
        for ln in all_lines:
            if L.is_boilerplate(ln.text):
                header_end = ln.top + 1
                break
    if header_end is None:
        header_end = height * 0.4
        inv.warnings.append("nie znaleziono granicy nagłówka – użyto 40% wysokości strony")

    split_x = min(width * 0.56, 335.0)   # prawy blok zaczyna się przy x≈342; lewy adres może być długi
    right = _build_lines([w for w in words if w.top < header_end and w.x0 >= split_x])
    left = _build_lines([w for w in words if w.top < header_end and w.x0 < split_x])
    body = [ln for ln in all_lines if ln.top >= header_end]
    # dokument dwujęzyczny (np. BE: strona 1 NL, strona 2 FR) – używamy pierwszej wersji
    hdr_idx = [i for i, ln in enumerate(body) if _is_address_header(ln.text)]
    if len(hdr_idx) > 1:
        second_top = body[hdr_idx[1]].top
        page_of_second = int(second_top // (height + 50))
        page_start = next((i for i, ln in enumerate(body) if ln.top >= page_of_second * (height + 50)), hdr_idx[1])
        body = body[: min(page_start, hdr_idx[1])]
        inv.notes.append("dokument wielojęzyczny – odczytano pierwszą wersję językową")

    try:
        _parse_header(right, left, inv, stem_number)
    except Exception as exc:  # noqa: BLE001
        inv.warnings.append(f"błąd parsowania nagłówka: {exc}")
    try:
        _parse_address_block(body, inv)
    except Exception as exc:  # noqa: BLE001
        inv.warnings.append(f"błąd parsowania adresów: {exc}")

    # zamówienie
    v = _kv_first(body, "order_date")
    if v is not None:
        inv.order_date = parse_date_text(v)
    v = _kv_first(body, "order_number")
    m = ORDER_NO_RE.search(v or "") or ORDER_NO_RE.search(text)
    inv.order_number = m.group(0) if m else (v or None)

    try:
        end = _parse_items(body, inv)
    except Exception as exc:  # noqa: BLE001
        inv.warnings.append(f"błąd parsowania pozycji: {exc}")
        end = 0
    try:
        _parse_totals(body, end, inv)
    except Exception as exc:  # noqa: BLE001
        inv.warnings.append(f"błąd parsowania sum: {exc}")

    # numer faktury: etykieta -> nazwa pliku -> token znany z CSV -> dowolny token
    if not inv.invoice_number and stem_number:
        inv.invoice_number, inv.invoice_number_source = stem_number, "nazwa pliku"
    if not inv.invoice_number:
        vat_ids = {x for x in (inv.seller_vat_id, inv.billing.vat_id, inv.shipping.vat_id, inv.buyer_header.vat_id, inv.seller.vat_id) if x}
        tokens = [t for t in INVOICE_NO_RE.findall(text.upper())
                  if t not in vat_ids and not NON_INVOICE_TOKEN_RE.match(t) and t != inv.original_invoice_number]
        hit = next((t for t in tokens if t in known), None) or (tokens[0] if tokens else None)
        if hit:
            inv.invoice_number, inv.invoice_number_source = hit, "tekst"
    if inv.invoice_number and stem_number and stem_number != inv.invoice_number:
        inv.warnings.append(
            f"numer z pliku ({stem_number}) różni się od numeru z treści ({inv.invoice_number})"
        )
    if not inv.invoice_number:
        inv.warnings.append("nie rozpoznano numeru faktury")
    if inv.invoice_number and inv.doc_type == "unknown":
        inv.doc_type = "invoice"
    if inv.invoice_total is None and inv.total_to_pay is not None:
        inv.invoice_total = inv.total_to_pay
    if inv.invoice_total is None:
        inv.warnings.append("nie rozpoznano sumy faktury")
    if inv.invoice_total is not None and inv.total_to_pay is not None and abs(inv.invoice_total - inv.total_to_pay) > 0.011:
        inv.warnings.append(f"suma faktury ({inv.invoice_total}) różni się od 'do zapłaty' ({inv.total_to_pay})")
    if not inv.items:
        inv.warnings.append("nie rozpoznano pozycji faktury")
    if inv.invoice_date is None:
        inv.warnings.append("brak daty faktury")
    if inv.billing.empty and inv.buyer_header.empty:
        inv.warnings.append("brak adresu nabywcy")
    return inv


def parse_pdfs(paths: Iterable[str | Path], known_invoice_numbers: Iterable[str] | None = None) -> list[Invoice]:
    known = list(known_invoice_numbers or [])
    out = []
    for p in paths:
        inv = parse_pdf(p, known)
        log.info("PDF %s -> %s (%s) ostrzeżeń: %d", inv.file, inv.invoice_number, inv.language, len(inv.warnings))
        out.append(inv)
    return out


def iter_pdf_paths(sources: Iterable[str | Path]) -> list[Path]:
    """Pliki .pdf z listy plików / katalogów (rekurencyjnie), posortowane."""
    found: list[Path] = []
    for s in sources:
        p = Path(s)
        if p.is_dir():
            found.extend(sorted(p.rglob("*.pdf")))
            found.extend(sorted(p.rglob("*.PDF")))
        elif p.is_file():
            found.append(p)
    seen, uniq = set(), []
    for p in found:
        if p.resolve() not in seen:
            seen.add(p.resolve())
            uniq.append(p)
    return uniq
