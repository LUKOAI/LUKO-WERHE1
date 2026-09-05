"""Ekstrakcja cech produktu z nazwy (tytul Amazon DE/PL lub nazwa z Apilo).

Cel: wspolny klucz produktu dla danych z 2020-2026, gdzie ten sam towar
wystepuje pod niemieckim tytulem (2020-22), polskim tytulem (2023-26)
i krotka nazwa z Apilo z kodem SKU (2026-07+).

Wynik :class:`Features`: rodzina, srednica [mm], dlugosc [mm], uchwyt,
liczba sztuk w zestawie, kod ostrza, flagi.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Optional

# ---------------------------------------------------------------------------
# slowniki rodzin (DE / PL / EN) - kolejnosc ma znaczenie (pierwsze trafienie)
# ---------------------------------------------------------------------------
FAMILY_PATTERNS: list[tuple[str, str]] = [  # (rodzina, regex rdzeni; poczatek slowa, bez konca)
    # zestawy najpierw (zeby "zestaw dlut" nie trafil w "dluto")
    ("set_chisel", r"(?<![a-ząćęłńóśźżäöüß])(meißelsatz|meissel\s*set|meißel\s*set|zestaw dłut|zestaw\s+dlut|chisel set|3-?teilig|3-?tlg|3-?częściowy|3-?czesciowy|zestaw szpic|zestaw dłut)"),
    ("set_drill", r"(?<![a-ząćęłńóśźżäöüß])(zestaw wierteł|bohrer[- ]?set|bohrersatz)"),
    ("set_adapter", r"(?<![a-ząćęłńóśźżäöüß])(zestaw adapterów|adapter[- ]?set|adaptersatz)"),
    ("blade_jigsaw", r"(?<![a-ząćęłńóśźżäöüß])(stichsägeblatt|stichsägeblätter|stichsägeblätt|brzeszczot(y|ów)? do wyrzynarki|nożyk|nozyk|jigsaw)"),
    ("blade_recip", r"(?<![a-ząćęłńóśźżäöüß])(säbelsägeblatt|säbelsägeblätter|brzeszczot(y)? do piły szablastej|piły szablastej|reciprocating)"),
    ("saw_disc", r"(?<![a-ząćęłńóśźżäöüß])(tarcza|kreissägeblatt|sägeblatt für|sägeblatt \d)"),
    ("grease", r"(?<![a-ząćęłńóśźżäöüß])(smar|fett|schmierfett|grease|mos2)"),
    ("tamper", r"(?<![a-ząćęłńóśźżäöüß])(stampferplatte|płyta ubijająca|plyta ubijajaca|tamper|verdichter|ubijak)"),
    ("driver_pile", r"(?<![a-ząćęłńóśźżäöüß])(wbijak do pali|pobijak do pali|pfahl(ramme|treiber)|post driver|picket|pobijak do słupków|pobijak do slupkow|wbijak do słupków|star picket|zaunpfahl)"),
    ("driver_rod", r"(?<![a-ząćęłńóśźżäöüß])(pobijak|wbijak|erdungsstab|erdnagel|eintreiber|gwoździowkrętak|gwozdziowkretak|uziom|kotew|ground rod|rod driver|nageleintreiber|wbijania)"),
    ("extension", r"(?<![a-ząćęłńóśźżäöüß])(przedłużk|przedluzk|przedłużacz|przedluzacz|verlängerung|bohrverlängerung|extension|verlangerung)"),
    ("adapter", r"(?<![a-ząćęłńóśźżäöüß])(adapter|adaptor|mufa|reduktion|übergang|przejściówka|przejsciowka)"),
    ("auger_garden", r"(?<![a-ząćęłńóśźżäöüß])(świder ogrodowy|swider ogrodowy|świder glebowy do wiertarki|gartenbohrer|pflanzbohrer|blumenbohrer|garden auger)"),
    ("auger", r"(?<![a-ząćęłńóśźżäöüß])(erdbohrer|pfahlbohrer|brunnenbohrer|świder|swider|wiertło do ziemi|wiertlo do ziemi|wiertło ziemne|wiertlo ziemne|earth auger|auger|earthmover|do ślimaka|do slimaka|ślimak|wiertarka do uziemienia|wiertarka do ślimaka|wiertło do gleby|wiertlo do gleby)"),
    ("chisel_gouge", r"(?<![a-ząćęłńóśźżäöüß])(bruzdownik|kanalmeißel|rillenmeißel|hohlmeißel|gouge)"),
    ("chisel_spade", r"(?<![a-ząćęłńóśźżäöüß])(spatmeißel|spatmeissel|schaufelmeißel|schaufelmeissel|dłuto łopatkowe|dluto lopatkowe|dłuto łopatowe|dłuto szerokie|dluto szerokie|breitmeißel|breitmeissel|spade chisel|wide chisel|dłuto płaskie szerokie)"),
    ("chisel_point", r"(?<![a-ząćęłńóśźżäöüß])(spitzmeißel|spitzmeissel|szpicak|szpic|dłuto szpiczaste|point chisel|spitz)"),
    ("chisel_bush", r"(?<![a-ząćęłńóśźżäöüß])(groszkownik|stockerplatte|stocker|bush hammer|busz|zęb(y|ów)|zähne)"),
    ("chisel_flat", r"(?<![a-ząćęłńóśźżäöüß])(flachmeißel|flachmeissel|dłuto płaskie|dluto plaskie|flat chisel|dłuto do betonu|dluto do betonu|dłuto|dluto|meißel|meissel|chisel)"),
    ("drill_bit", r"(?<![a-ząćęłńóśźżäöüß])(betonbohrer|hammerbohrer|steinbohrer|wiertło do betonu|wiertlo do betonu|wiertło udarowe|wiertlo udarowe|wiertarka do betonu|wiertarka do kamienia|drill bit|bohrer für beton|wiertło sds|wiertlo sds)"),
    ("hole_saw", r"(?<![a-ząćęłńóśźżäöüß])(lochsäge|betonlochsäge|otwornic|koronk|kernbohrer|hole saw|bohrkrone)"),
    ("pin", r"(?<![a-ząćęłńóśźżäöüß])(zawleczk|sworzeń|sworzen|bolec|splint|sicherungsstift|quick pin|clip)"),
    ("handle", r"(?<![a-ząćęłńóśźżäöüß])(uchwyt typu t|t-griff|t-handle|gryf|handle)"),
    ("spring", r"(?<![a-ząćęłńóśźżäöüß])(sprężyn|sprezyn|feder|spring)"),
    ("string", r"(?<![a-ząćęłńóśźżäöüß])(sznur|schnur|string)"),
]

SHANK_PATTERNS: list[tuple[str, str]] = [
    ("sds_max", r"sds[\s-]*max"),
    ("sds_plus", r"sds[\s-]*plus"),
    ("hex28", r"(hex|sechskant|sześciok|szesciok)[\s-]*28|28\s*mm\s*(hex|sechskant|sześciok)"),
    ("hex30", r"(hex|sechskant|sześciok|szesciok)[\s-]*30|30\s*mm\s*(hex|sechskant|sześciok|sześciokąt)|sds[\s-]*hex|hex[\s-]*30"),
    ("hex", r"\bhex\b|sechskant|sześciok|szesciok"),
    ("m14", r"\bm[\s-]?14\b"),
    ("m18", r"\bm[\s-]?18\b"),
    ("unc_1_1_4", r"1[\s.,]?1/4"),
    ("unf_1_2", r"1/2[\s-]*20"),
    ("shank20", r"(uchwyt|aufnahme|schaft|chwyt)\s*20\s*mm|20\s*mm\s*(uchwyt|aufnahme|schaft|chwyt)"),
]

BLADE_CODE_RE = re.compile(r"\b([TS]\s?\d{3,4}\s?[A-Z]{0,3}\d?)\b")
NUM = r"(\d+(?:[.,]\d+)?)"
DIM_PAIR_RE = re.compile(NUM + r"\s*(?:mm)?\s*[x×X]\s*" + NUM + r"\s*(mm|cm)?")
DIAM_RE = re.compile(r"(?:ø|⌀|Ø|durchmesser|średnic\w*|srednic\w*|\bd\b)\s*(?:wewnętrzna|wewnetrzna|innen)?\s*" + NUM + r"\s*(mm|cm)?", re.I)
LEN_RE = re.compile(r"(?:długość|dlugosc|länge|laenge|lang|długości|dlugosci|length)\s*(?:robocza)?\s*:?\s*" + NUM + r"\s*(mm|cm)", re.I)
MM_RE = re.compile(NUM + r"\s*(mm|cm)\b", re.I)
COUNT_RE = re.compile(r"\b(\d+)\s*(?:x|×|szt\.?|sztuk|stück|stk|tlg|teilig|częściow\w*|czesciow\w*|op\.?|pack|-?piece)\b", re.I)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _to_mm(v: float, unit: Optional[str]) -> float:
    if unit and unit.lower() == "cm":
        return v * 10
    return v


@dataclass
class Features:
    family: str = "other"
    brand: Optional[str] = None
    diameter_mm: Optional[float] = None
    length_mm: Optional[float] = None
    shank: Optional[str] = None
    shank2: Optional[str] = None
    count: Optional[int] = None
    blade_code: Optional[str] = None
    double_spiral: bool = False
    premium: bool = False
    dims_raw: list[tuple[float, float]] = field(default_factory=list)

    def key(self) -> str:
        """Kanoniczny klucz produktu (bez marki - WERHE i WERKON to ten sam towar w innym opakowaniu)."""
        parts = [self.family]
        if self.blade_code:
            parts.append(self.blade_code)
        if self.diameter_mm is not None:
            parts.append(f"d{self.diameter_mm:g}")
        if self.length_mm is not None:
            parts.append(f"l{self.length_mm:g}")
        if self.shank:
            parts.append(self.shank)
        if self.shank2:
            parts.append(self.shank2)
        if self.count and self.family.startswith(("blade", "set", "pin")):
            parts.append(f"n{self.count}")
        if self.double_spiral:
            parts.append("dbl")
        return "|".join(parts)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["key"] = self.key()
        return d


def extract(name: str) -> Features:
    f = Features()
    raw = name
    low = name.lower()
    low_ascii = strip_accents(low)

    # marka
    if re.search(r"\bwerkon\b", low):
        f.brand = "WERKON"
    elif re.search(r"\bwerhe\b", low):
        f.brand = "WERHE"

    # rodzina: zestawy maja priorytet, poza tym wygrywa najwczesniejsze slowo kluczowe w nazwie
    best: Optional[tuple[int, int, str]] = None
    for order, (fam, pat) in enumerate(FAMILY_PATTERNS):
        m = re.search(pat, low, re.I) or re.search(pat, low_ascii, re.I)
        if not m:
            continue
        prio = 0 if fam.startswith("set_") else 1
        cand = (prio, m.start(), fam)
        if best is None or cand < best:
            best = cand
    if best:
        f.family = best[2]

    # uchwyty (moze byc dwa, np. adapter SDS Max -> M14)
    shanks = []
    for sh, pat in SHANK_PATTERNS:
        if re.search(pat, low, re.I) or re.search(pat, low_ascii, re.I):
            if sh == "hex" and any(s.startswith("hex") for s in shanks):
                continue
            shanks.append(sh)
    if shanks:
        f.shank = shanks[0]
        if len(shanks) > 1:
            f.shank2 = shanks[1]

    # kod ostrza (T744D, T344CB, S1243HM, T119BO, T218A, T1044D, T225B, T544D, T718GF)
    m = BLADE_CODE_RE.search(raw.replace(" ", "") if False else raw)
    if m and f.family.startswith("blade"):
        f.blade_code = m.group(1).replace(" ", "").upper()
    elif f.family.startswith("blade"):
        m2 = re.search(r"\b([TS]\d{3,4}[A-Z]{0,3}\d?)\b", raw.upper())
        if m2:
            f.blade_code = m2.group(1)

    # wymiary: pary AxB
    for m in DIM_PAIR_RE.finditer(raw):
        a, b, unit = _num(m.group(1)), _num(m.group(2)), m.group(3)
        f.dims_raw.append((_to_mm(a, unit), _to_mm(b, unit)))
    # srednica jawna
    m = DIAM_RE.search(raw)
    if m:
        f.diameter_mm = _to_mm(_num(m.group(1)), m.group(2))
    # dlugosc jawna
    m = LEN_RE.search(raw)
    if m:
        f.length_mm = _to_mm(_num(m.group(1)), m.group(2))

    # heurystyki wg rodziny
    mm_values = [_to_mm(_num(a), u) for a, u in MM_RE.findall(raw)]
    if f.dims_raw:
        a, b = f.dims_raw[0]
        if f.family in ("drill_bit", "chisel_flat", "chisel_spade", "chisel_point", "chisel_gouge", "driver_rod", "driver_pile", "auger_garden", "auger", "tamper", "chisel_bush", "extension"):
            if f.diameter_mm is None:
                f.diameter_mm = min(a, b) if f.family not in ("driver_pile",) else a
            if f.length_mm is None:
                f.length_mm = max(a, b)
    if f.family in ("auger", "auger_garden") and f.diameter_mm is None:
        # pierwsza wartosc mm <= 300 to srednica; wartosc >= 300 lub w cm to dlugosc
        cands = [v for v in mm_values if 20 <= v <= 300]
        if cands:
            f.diameter_mm = cands[0]
        longs = [v for v in mm_values if v > 300]
        if longs and f.length_mm is None:
            f.length_mm = longs[0]
    if f.family == "extension" and f.length_mm is None:
        longs = [v for v in mm_values if v >= 100]
        if longs:
            f.length_mm = longs[0]
    if f.family in ("driver_rod",) and f.diameter_mm is None:
        cands = [v for v in mm_values if 5 <= v <= 60]
        if cands:
            f.diameter_mm = cands[0]
    if f.family in ("driver_pile",) and f.diameter_mm is None:
        cands = [v for v in mm_values if 40 <= v <= 200]
        if cands:
            f.diameter_mm = cands[0]
    if f.family in ("drill_bit", "chisel_flat", "chisel_spade", "chisel_point", "chisel_bush", "chisel_gouge") and f.diameter_mm is None:
        cands = [v for v in mm_values if 4 <= v <= 150]
        if cands:
            f.diameter_mm = cands[0]
        longs = [v for v in mm_values if v >= 100 and v != f.diameter_mm]
        if longs and f.length_mm is None:
            f.length_mm = longs[0]
    if f.family in ("blade_jigsaw", "blade_recip") and f.length_mm is None:
        longs = [v for v in mm_values if 50 <= v <= 400]
        if longs:
            f.length_mm = longs[0]
    if f.family == "grease" and f.diameter_mm is None:
        m = re.search(r"(\d+)\s*ml", low)
        if m:
            f.diameter_mm = float(m.group(1))  # pojemnosc [ml] w polu diameter (umownie)

    # liczba sztuk
    m = COUNT_RE.search(raw)
    if m:
        f.count = int(m.group(1))
    if f.family.startswith("set") and f.count is None:
        m = re.search(r"(\d)\s*[-]?\s*(tlg|teilig|częściowy|czesciowy)", low)
        f.count = int(m.group(1)) if m else 3

    # flagi
    if re.search(r"doppel[- ]?welle|doppelspiral|podwójn\w* spiral|podwojn\w* spiral|podwójny wa[łl]|double spiral|dwuspiral|podw", low):
        f.double_spiral = True
    if re.search(r"premium", low):
        f.premium = True
    return f


# --------------------------------------------------------------------------- #
# Length estimation (longest side) — used by the FC rule when the catalog has no
# dimensions. Ported from the historical analysis (docs/analiza/fc_rules.md).
# --------------------------------------------------------------------------- #
SHORT_FAMILIES = {"adapter", "driver_rod", "driver_pile", "blade_jigsaw", "blade_recip", "chisel_bush", "grease", "pin",
                  "spring", "string", "set_adapter", "set_drill", "tamper", "saw_disc", "hole_saw"}
_AUGER_KW = re.compile(r"(świder|swider|ziemn|uziemiaj|wiertnic|gruntow|runo|do ziemi|erdbohrer|ślimak|slimak|auger|"
                       r"earthmover|wiertło do pali|do gleby|lodu|pflanzbohrer)", re.I)
_NOT_AUGER = re.compile(r"przedłuż|przedluz|słupek|slupek|drążek|drazek|uchwyt do|adapter|bolzen|sworz", re.I)
_ADAPTER_IS_AUGER = re.compile(r"^(WERHE\s*®?\s*)?(Wiert|Zestaw świdr)", re.I)
_NUMF = r"(\d+(?:[.,]\d+)?)"


def auger_like(name: str, family: str) -> bool:
    if family == "auger":
        return True
    if family == "other" and _AUGER_KW.search(name) and not _NOT_AUGER.search(name):
        return True
    if family == "adapter" and _ADAPTER_IS_AUGER.search(name):
        return True
    return False


def parse_length_mm(name: str, auger: bool = False) -> Optional[float]:
    """Longest dimension mentioned in a product title, in mm (None when nothing found)."""
    n = name
    cands: list[float] = []
    for m in re.finditer(_NUMF + r"\s*mm\s*d[łl]ugo", n, re.I):
        cands.append(float(m.group(1).replace(",", ".")))
    for m in re.finditer(r"d[łl]\.?\s*" + _NUMF + r"\s*cm", n, re.I):
        cands.append(10 * float(m.group(1).replace(",", ".")))
    for m in re.finditer(r"(?<![\d.,])(\d{2,3})\s*cm\b", n, re.I):
        cands.append(10 * float(m.group(1)))
    for m in re.finditer(_NUMF + r"\s*[xX×]\s*" + _NUMF + r"\s*[xX×]\s*" + _NUMF, n):
        cands.append(float(m.group(3).replace(",", ".")))
    for m in re.finditer(_NUMF + r"\s*[xX×]\s*" + _NUMF + r"\s*(?:mm|$|\b)", n):
        b = float(m.group(2).replace(",", "."))
        if b >= 40:
            cands.append(b)
    if not auger:
        for m in re.finditer(r"(?<![\d.,xX×/])(\d{3,4})\s*mm\b", n):
            pre = n[max(0, m.start() - 6):m.start()]
            if re.search(r"[ØÖ⌀]|-\s*$|–\s*$", pre):
                continue
            cands.append(float(m.group(1)))
    return max(cands) if cands else None


def estimate_length_mm(name: str, features: Optional[Features] = None) -> tuple[Optional[float], bool]:
    """(length_mm, is_default). Family defaults: earth augers without a stated length ≈ 800 mm,
    handles 560 mm, small hardware 150 mm."""
    f = features or extract(name)
    if f.length_mm is not None:
        return f.length_mm, False
    aug = auger_like(name, f.family or "")
    p = parse_length_mm(name, auger=aug)
    if p is not None:
        return p, False
    if aug:
        return 800.0, True
    if f.family == "handle":
        return 560.0, True
    if f.family in SHORT_FAMILIES or f.family == "other":
        return 150.0, True
    return None, True
