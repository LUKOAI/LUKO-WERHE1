"""Parser faktur Amazon VCS (PDF) oparty na współrzędnych słów (pdfplumber).

Układ faktury Amazon jest stały niezależnie od języka:
  * prawy górny blok: tytuł, status, referencja płatności, sprzedawca, NIP,
    data faktury, nr faktury, razem do zapłaty
  * lewy górny blok: adres nabywcy (WIELKIMI LITERAMI)
  * blok 3 kolumn: adres rozliczeniowy | adres dostawy | sprzedawca
  * sekcja zamówienia: data zamówienia, nr zamówienia
  * tabela pozycji (opis / ilość / cena / stawka / suma) z liniami "ASIN: ..."
  * koszty wysyłki, suma faktury, podsumowanie VAT, przeliczenie na walutę
    rejestracji (np. "CZK0.00"), przypisy.
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

INVOICE_NO_RE = re.compile(r"\b[A-Z]{2}[0-9A-Z]{12}\b")
ORDER_NO_RE = re.compile(r"\b\d{3}-\d{7}-\d{7}\b")
VAT_ID_RE = re.compile(r"\b[A-Z]{2}[0-9A-Z]{8,13}\b")
ASIN_RE = re.compile(r"\b(B0[0-9A-Z]{8}|\d{9}[0-9X])\b")
COUNTRY_LINE_RE = re.compile(r"^[A-Z]{2}$")
RATE_RE = re.compile(r"^(\d{1,2}(?:[.,]\d{1,2})?)\s?%$")
CONVERSION_RE = re.compile(r"^([A-Z]{3})\s?([-−–]?\d[\d.,\s]*)$")
_AMOUNT_CORE = r"[-−–]?\d{1,3}(?:[  .,]\d{3})*(?:[.,]\d{1,2})?|[-−–]?\d+(?:[.,]\d{1,2})?"
AMOUNT_TOKEN_RE = re.compile(
    r"^(?P<pre>[€£$]|zł|kr|kč|[A-Z]{3})?\s?(?P<num>" + _AMOUNT_CORE + r")\s?(?P<post>[€£$]|zł|kr|kč|[A-Z]{3})?$",
    re.IGNORECASE,
)
STREET_VAT_RE = re.compile(
    r",?\s*(?:nip|p\.? ?iva|partita iva|tva|ust-?idnr\.?|ust-?id|nif|cif|btw(?:-nummer|-id)?|"
    r"vat(?: no\.?| number| id)?|momsreg\.? ?nr|dič)\s*:?\s*([A-Z]{2}[0-9A-Z]{8,13})\s*$",
    re.IGNORECASE,
)
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
    vat_id: str | None = None
    city_line: str | None = None
    lines: list[str] = field(default_factory=list)

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
    doc_type: str = "unknown"          # invoice | credit_note | unknown
    title: str | None = None
    language: str = "unknown"
    paid: bool | None = None
    payment_reference: str | None = None
    seller_name: str | None = None
    seller_vat_id: str | None = None
    invoice_date: date | None = None
    order_date: date | None = None
    order_number: str | None = None
    total_to_pay: float | None = None
    invoice_total: float | None = None
    shipping_gross: float | None = None
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

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("invoice_date", "order_date"):
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
    s = str(token).strip().replace(" ", " ").replace(" ", "")
    if not s:
        return None
    neg = s[0] in "-−–"
    s = s.lstrip("-−–")
    if not re.fullmatch(r"\d[\d.,]*", s):
        return None
    int_part, frac = s, "00"
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
    """Rozpoznaje token kwoty (z opcjonalnym symbolem waluty) -> (kwota, waluta)."""
    m = AMOUNT_TOKEN_RE.match(token.strip())
    if not m:
        return None
    num = m.group("num")
    # sam integer bez separatora dziesiętnego i bez symbolu waluty to nie kwota
    if not re.search(r"[.,]\d{1,2}$", num) and not (m.group("pre") or m.group("post")):
        return None
    val = parse_amount(num)
    if val is None:
        return None
    sym = (m.group("pre") or m.group("post") or "").strip()
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


def _extract_words(path: Path) -> tuple[list[Word], float, float, str]:
    import pdfplumber  # import lokalny – ciężka zależność

    words: list[Word] = []
    texts: list[str] = []
    width = height = 0.0
    with pdfplumber.open(str(path)) as pdf:
        for pno, page in enumerate(pdf.pages):
            width, height = float(page.width), float(page.height)
            offset = pno * (height + 50)
            for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
                words.append(Word(w["text"], float(w["x0"]), float(w["x1"]), float(w["top"]) + offset))
            texts.append(page.extract_text() or "")
    return words, width, height, "\n".join(texts)


def _first_label_line(lines: list[Line], key: str) -> int | None:
    for i, ln in enumerate(lines):
        if L.match_label(ln.text, key) is not None:
            return i
    return None


def _line_contains_label(text: str, key: str) -> bool:
    t = L.norm(text)
    return any(lbl in t for lbl in L.NORM_LABELS[key])


# ---------------------------------------------------------------------------
# adresy
# ---------------------------------------------------------------------------
def parse_address(lines: list[str]) -> Address:
    lines = [ln.strip() for ln in lines if ln and ln.strip()]
    addr = Address(lines=list(lines))
    if not lines:
        return addr
    addr.name = lines[0]
    idx_country = None
    for i in range(len(lines) - 1, 0, -1):
        if COUNTRY_LINE_RE.match(lines[i]):
            idx_country = i
            break
    if idx_country is not None:
        addr.country = lines[idx_country]
        middle = lines[1:idx_country]
        after = lines[idx_country + 1:]
    else:
        middle = lines[1:]
        after = []
    for ln in after:
        m = VAT_ID_RE.search(ln)
        if m and not addr.vat_id:
            addr.vat_id = m.group(0)
    if middle:
        addr.city_line = middle[-1]
        street_lines = []
        for ln in middle[:-1]:
            m = STREET_VAT_RE.search(ln)
            if m:
                addr.vat_id = addr.vat_id or m.group(1)
                ln = ln[: m.start()].rstrip(" ,")
            if ln:
                street_lines.append(ln)
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
                # "Homburg 66424" bez przecinka
                m = re.match(r"^(.*?)[\s,]+([A-Z0-9][A-Z0-9 -]{2,9})$", parts[0])
                if m and re.search(r"\d", m.group(2)):
                    addr.city, postal = m.group(1).strip(), m.group(2)
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


def _parse_address_block(body: list[Line], inv: Invoice) -> None:
    hi = None
    for i, ln in enumerate(body):
        if _line_contains_label(ln.text, "billing_address") or _line_contains_label(ln.text, "shipping_address"):
            hi = i
            break
    if hi is None:
        inv.warnings.append("brak nagłówka bloku adresów (adres rozliczeniowy / dostawy)")
        return
    header = body[hi]
    starts = _split_columns(header)
    # role kolumn wg etykiet w nagłówku
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
    if inv.billing.empty:
        inv.warnings.append("pusty adres rozliczeniowy")


# ---------------------------------------------------------------------------
# nagłówek (prawa / lewa kolumna)
# ---------------------------------------------------------------------------
def _kv_from_lines(lines: list[Line], key: str) -> str | None:
    for i, ln in enumerate(lines):
        v = L.match_label(ln.text, key)
        if v is None:
            continue
        if v:
            return v
        # wartość w następnej linii (np. długa referencja płatności)
        if i + 1 < len(lines):
            nxt = lines[i + 1].text
            if not any(L.match_label(nxt, k) is not None for k in L.LABELS):
                return nxt.strip()
        return ""
    return None


def _parse_header(right: list[Line], left: list[Line], inv: Invoice) -> None:
    if right:
        title = right[0].text.strip()
        inv.title = title
        nt = L.norm(title)
        if nt in {L.norm(t) for t in L.DOC_TITLES_CREDIT}:
            inv.doc_type = "credit_note"
        elif nt in {L.norm(t) for t in L.DOC_TITLES_INVOICE}:
            inv.doc_type = "invoice"
    for ln in right:
        if L.match_label(ln.text, "paid") is not None and L.norm(ln.text) in L.NORM_LABELS["paid"]:
            inv.paid = True
    inv.payment_reference = _kv_from_lines(right, "payment_reference") or None
    inv.seller_name = _kv_from_lines(right, "seller") or None
    v = _kv_from_lines(right, "vat_id")
    if v:
        m = VAT_ID_RE.search(v)
        inv.seller_vat_id = m.group(0) if m else v
    v = _kv_from_lines(right, "invoice_date")
    if v is not None:
        inv.invoice_date = parse_date_text(v)
        if inv.invoice_date is None:
            inv.warnings.append(f"nie rozpoznano daty faktury: {v!r}")
    v = _kv_from_lines(right, "invoice_number")
    if v:
        m = INVOICE_NO_RE.search(v.upper())
        inv.invoice_number = m.group(0) if m else v.strip()
        inv.invoice_number_source = "etykieta"
    v = _kv_from_lines(right, "total_to_pay")
    if v:
        toks = [amount_token(t) for t in v.split()]
        toks = [t for t in toks if t]
        if toks:
            inv.total_to_pay, cur = toks[-1]
            inv.currency = inv.currency or cur
        else:
            # np. "121,87 zł" rozbite na tokeny
            a = amount_token(v.replace(" ", ""))
            if a:
                inv.total_to_pay, cur = a
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


def _numbers_from_words(words: list[Word]) -> dict:
    out: dict = {"qty": None, "rate": None, "amounts": [], "currency": None}
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
        # kwota + osobny symbol waluty
        joined = t
        if i + 1 < len(toks) and toks[i + 1].lower() in L.CURRENCY_SYMBOLS:
            joined = t + toks[i + 1]
        a = amount_token(joined)
        if a is None and i + 1 < len(toks):
            a2 = amount_token(t + toks[i + 1])
            if a2:
                a = a2
                i += 1
        if a:
            out["amounts"].append(a[0])
            out["currency"] = out["currency"] or a[1]
            if joined != t:
                i += 1
        i += 1
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
    # pomiń linie nagłówka tabeli (do pierwszej linii z ASIN / kwotą / do 'koszty wysyłki')
    i = hi + 1
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
        desc = re.sub(r"\s+", " ", desc).strip(" ,")
        item.description = desc or None
        inv.items.append(item)

    while i < len(body):
        ln = body[i]
        t = L.norm(ln.text)
        if L.match_label(ln.text, "shipping") is not None or L.match_label(ln.text, "invoice_total") is not None:
            end = i
            break
        # nagłówek podsumowania VAT kończy tabelę – ale tylko gdy mamy już pozycje
        # (nagłówek tabeli pozycji też zawiera 'stawka podatku' / 'taux tva')
        if _line_contains_label(ln.text, "vat_summary_header") and inv.items and not block:
            end = i
            break
        # linie nagłówka tabeli: same etykiety kolumn / nawiasy
        only_header = all(
            L.norm(w.text) in header_words or re.fullmatch(r"[()\w./-]*", L.norm(w.text)) and not re.search(r"\d", w.text)
            for w in ln.words
        ) and not any(w.x0 < qty_x - 5 and re.search(r"\d", w.text) for w in ln.words)
        if not block and only_header and not ASIN_RE.search(ln.text) and not any(
            amount_token(w.text) for w in ln.words
        ):
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
    for ln in body[start:]:
        text = ln.text
        nums = _numbers_from_words(ln.words)
        if L.match_label(text, "shipping") is not None and nums["amounts"]:
            inv.shipping_gross = nums["amounts"][-1]
            continue
        if L.match_label(text, "invoice_total") is not None and nums["amounts"]:
            inv.invoice_total = nums["amounts"][-1]
            inv.currency = inv.currency or nums["currency"]
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
            inv.shipped_from = v.lstrip(": ").strip() or None
            continue
        v = L.match_label(text, "exchange_rate")
        if v is not None:
            m2 = re.search(r"\d+[.,]\d+", v)
            if m2:
                inv.exchange_rate = parse_amount(m2.group(0))
            continue
        if re.match(r"^\(\d+\)", text.strip()) and not nums["amounts"]:
            inv.notes.append(text.strip())
            continue
        if in_summary:
            first = ln.words[0].text if ln.words else ""
            starts_with_rate = bool(RATE_RE.match(first)) or (
                len(ln.words) > 1 and ln.words[1].text == "%" and re.fullmatch(r"\d{1,2}(?:[.,]\d{1,2})?", first)
            )
            if starts_with_rate and nums["rate"] is not None and len(nums["amounts"]) == 2:
                am = nums["amounts"]
                inv.vat_lines.append(VatLine(nums["rate"], am[0], am[1]))
                continue
            if L.match_label(text, "summary_total") is not None and nums["amounts"]:
                am = nums["amounts"]
                inv.total_net = am[0]
                inv.total_vat = am[1] if len(am) > 1 else None
                continue
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
    try:
        words, width, height, text = _extract_words(path)
    except Exception as exc:  # noqa: BLE001 – każdy błąd odczytu ma być raportowany, nie rzucany
        inv.warnings.append(f"nie udało się odczytać PDF: {exc}")
        return inv
    inv.text = text
    inv.language = L.detect_language(text)
    if not words:
        inv.warnings.append("PDF nie zawiera tekstu (skan?) – wymagane OCR")
        return inv
    all_lines = _build_lines(words)

    # koniec nagłówka: linia z nagłówkiem bloku adresów albo boilerplate 'contact-us'
    header_end = None
    for ln in all_lines:
        if _line_contains_label(ln.text, "billing_address") or _line_contains_label(ln.text, "shipping_address"):
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

    split_x = width / 2.0
    right = _build_lines([w for w in words if w.top < header_end and w.x0 >= split_x])
    left = _build_lines([w for w in words if w.top < header_end and w.x0 < split_x])
    body = [ln for ln in all_lines if ln.top >= header_end]

    try:
        _parse_header(right, left, inv)
    except Exception as exc:  # noqa: BLE001
        inv.warnings.append(f"błąd parsowania nagłówka: {exc}")
    try:
        _parse_address_block(body, inv)
    except Exception as exc:  # noqa: BLE001
        inv.warnings.append(f"błąd parsowania adresów: {exc}")

    # zamówienie
    v = _kv_from_lines(body, "order_date")
    if v is not None:
        inv.order_date = parse_date_text(v)
    v = _kv_from_lines(body, "order_number")
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
    stem_m = INVOICE_NO_RE.search(path.stem.upper())
    if not inv.invoice_number and stem_m:
        inv.invoice_number, inv.invoice_number_source = stem_m.group(0), "nazwa pliku"
    if not inv.invoice_number:
        tokens = INVOICE_NO_RE.findall(text.upper())
        hit = next((t for t in tokens if t in known), None) or (tokens[0] if tokens else None)
        if hit:
            inv.invoice_number, inv.invoice_number_source = hit, "tekst"
    if inv.invoice_number and stem_m and stem_m.group(0) != inv.invoice_number:
        inv.warnings.append(
            f"numer z pliku ({stem_m.group(0)}) różni się od numeru z treści ({inv.invoice_number})"
        )
    if not inv.invoice_number:
        inv.warnings.append("nie rozpoznano numeru faktury")
    if inv.invoice_number and inv.doc_type == "unknown":
        inv.doc_type = "invoice"
    if inv.invoice_total is None and inv.total_to_pay is not None:
        inv.invoice_total = inv.total_to_pay
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
