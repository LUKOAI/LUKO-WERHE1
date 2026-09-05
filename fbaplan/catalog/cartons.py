"""Master-carton size inference when the catalog does not say how many units
fit in a carton: (1) the quantity module visible in recent history (line
quantities are multiples of full cartons), (2) carton modules derived from the
historical analysis (augers by diameter, extensions by length, ...).
See docs/analiza/composition.md §3."""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from ..history.store import SkuStats
from ..models import CartonSpec, Product
from .normalize import extract

AUGER_BY_DIAMETER = {40: 15, 50: 14, 60: 13, 80: 11, 100: 10, 120: 9, 150: 7, 200: 6}
EXTENSION_BY_LENGTH = {400: 34, 600: 24, 750: 14, 800: 20, 1000: 10, 1180: 9, 5000: 4}

# Apilo SKU codes carry the dimensions: 1ZWG80dp, 1WG150h, 1Wo60x600, 5PR750m-m, 3DB75x600m, 2WB40x600p
_AUGER_SKU = re.compile(r"^1(?:Z?WG|Wo)(?P<d>\d{2,3})(?:x(?P<l>\d{3,4}))?(?P<rest>[A-Za-z-]*)$")
_EXT_SKU = re.compile(r"^5PR(?P<l>\d{3,4})(?P<rest>[A-Za-z-]*)$")
_DIM_SKU = re.compile(r"^(?P<pre>[23][A-Za-z]+)(?P<d>\d{1,3}(?:,\d)?)x(?P<l>\d{3,4})(?P<rest>[A-Za-z0-9]*)$")


def infer_module_from_qtys(qty_counter: Counter, min_share: float = 0.6, min_lines: int = 3) -> Optional[int]:
    """Largest quantity module m (appearing itself as a line quantity) such that at least
    ``min_share`` of the lines are multiples of m. Example: 33×17, 11×11, 66×6, 22×3 -> 11."""
    total = sum(qty_counter.values())
    if total < min_lines:
        return None
    best: Optional[int] = None
    for m in sorted((q for q in qty_counter if q >= 2), reverse=True):
        share = sum(n for q, n in qty_counter.items() if q % m == 0) / total
        if share >= min_share and qty_counter[m] >= 1:
            best = m
            break
    return best


def module_from_analysis(product: Product) -> Optional[int]:
    sku = product.sku
    m = _AUGER_SKU.match(sku)
    if m:
        d = int(m.group("d"))
        if d in AUGER_BY_DIAMETER:
            if d == 60 and "m" in m.group("rest").lower() and "p" not in m.group("rest").lower():
                return 12
            return AUGER_BY_DIAMETER[d]
    m = _EXT_SKU.match(sku)
    if m:
        L = int(m.group("l"))
        if L in EXTENSION_BY_LENGTH:
            if L == 1000 and "m" not in m.group("rest").lower():
                return 30
            return EXTENSION_BY_LENGTH[L]
    ft = extract(product.name)
    fam = product.family or ft.family
    d = int(ft.diameter_mm) if ft.diameter_mm else None
    L = int(ft.length_mm) if ft.length_mm else None
    m = _DIM_SKU.match(sku)
    if m:
        try:
            d = d or int(float(m.group("d").replace(",", ".")))
            L = L or int(m.group("l"))
        except ValueError:
            pass
    if fam == "auger" and d in AUGER_BY_DIAMETER:
        return AUGER_BY_DIAMETER[d]
    if fam == "extension" and L in EXTENSION_BY_LENGTH:
        return EXTENSION_BY_LENGTH[L]
    if fam in ("chisel_flat", "chisel_spade"):
        if d == 75 and L == 600:
            return 14
        if d == 110 and L in (410, 460):
            return 7
        if d == 135 and L == 410:
            return 29
    if fam == "drill_bit" and d == 40 and L == 600:
        return 7
    if fam == "grease":
        return 100
    if fam == "blade_jigsaw":
        return 50
    return None


def infer_carton(product: Product, stats: Optional[SkuStats]) -> Optional[CartonSpec]:
    """Return an *estimated* CartonSpec for a product without one, or None."""
    if product.carton and product.carton.units_per_carton > 0:
        return None
    if stats and stats.qty_counter:
        m = infer_module_from_qtys(stats.qty_counter)
        if m and m > 1:
            return CartonSpec(units_per_carton=m, estimated=True)
    m = module_from_analysis(product)
    if m:
        return CartonSpec(units_per_carton=m, estimated=True)
    return None
