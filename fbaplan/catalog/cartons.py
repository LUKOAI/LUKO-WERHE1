"""Master-carton size inference when the catalog does not say how many units
fit in a carton: (1) the most common line quantity in recent history,
(2) carton modules derived from the historical analysis (augers by diameter,
extensions by length, ...). See docs/analiza/composition.md §3."""
from __future__ import annotations

from typing import Optional

from ..history.store import SkuStats
from ..models import CartonSpec, Product
from .normalize import extract

# family -> [(matcher on Features, units_per_carton)]
AUGER_BY_DIAMETER = {40: 15, 50: 14, 60: 13, 80: 11, 100: 10, 120: 9, 150: 7, 200: 6}
EXTENSION_BY_LENGTH = {400: 34, 600: 24, 750: 14, 800: 20, 1000: 10, 1180: 9, 5000: 4}


def module_from_analysis(product: Product) -> Optional[int]:
    ft = extract(product.name)
    fam = product.family or ft.family
    d = int(ft.diameter_mm) if ft.diameter_mm else None
    L = int(ft.length_mm) if ft.length_mm else None
    if fam == "auger" and d in AUGER_BY_DIAMETER:
        if d == 60 and ft.shank == "sds_max":
            return 12
        return AUGER_BY_DIAMETER[d]
    if fam == "extension" and L in EXTENSION_BY_LENGTH:
        if L == 1000 and ft.shank != "sds_max":
            return 30
        return EXTENSION_BY_LENGTH[L]
    if fam == "chisel_flat":
        if d == 75 and L == 600:
            return 14
        if d == 110 and L == 410:
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


def infer_carton(product: Product, stats: Optional[SkuStats], min_share: float = 0.4) -> Optional[CartonSpec]:
    """Return an *estimated* CartonSpec for a product without one, or None."""
    if product.carton and product.carton.units_per_carton > 0:
        return None
    if stats and stats.qty_counter:
        total = sum(stats.qty_counter.values())
        qty, n = stats.qty_counter.most_common(1)[0]
        if qty > 1 and n / total >= min_share:
            return CartonSpec(units_per_carton=qty, estimated=True)
    m = module_from_analysis(product)
    if m:
        return CartonSpec(units_per_carton=m, estimated=True)
    return None
