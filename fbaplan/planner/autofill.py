"""Automatic completion of a plan: keep adding full cartons — new fillers first
(up to ``max_new_skus`` distinct products), then top-ups of products already in
the plan — until the last pallet of the anchor FC reaches the target utilisation,
or, when the catalog has no dimensions, until the target number of units."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..history.store import HistoryStats
from ..models import Plan, PlanLine, Product, StockRow
from ..packing.fill import carton_for
from ..predict.fc import FCPredictor
from .filler import suggest
from .session import PlanEval, evaluate


@dataclass
class AutofillResult:
    added: list[tuple[str, int]] = field(default_factory=list)   # (sku, qty) in the order added
    stopped_because: str = ""
    final: Optional[PlanEval] = None


def _velocity(sku: str, stock: Optional[dict[str, StockRow]], stats: Optional[HistoryStats]) -> float:
    st = (stock or {}).get(sku)
    if st and (st.sales_30d or st.sales_90d):
        return st.daily_velocity * 30
    hs = stats.by_sku.get(sku) if stats else None
    return hs.units_12m / 12.0 if hs else 0.0


def _room_left(sku: str, qty_now: int, products: dict[str, Product], stock: Optional[dict[str, StockRow]]) -> int:
    """How many more units of sku may be added (max per plan, own stock)."""
    p = products[sku]
    limit = 10 ** 9
    if p.max_qty_per_plan:
        limit = min(limit, p.max_qty_per_plan - qty_now)
    st = (stock or {}).get(sku)
    if st and st.local_stock is not None:
        limit = min(limit, st.local_stock - qty_now)
    return max(0, limit)


def autofill(plan: Plan, products: dict[str, Product], predictor: FCPredictor,
             stock: Optional[dict[str, StockRow]] = None, stats: Optional[HistoryStats] = None,
             weights: Optional[dict] = None, target_fill: float = 0.9, target_units: int = 150,
             max_steps: int = 60, max_new_skus: int = 8, capacity_left_m3: Optional[float] = None) -> AutofillResult:
    res = AutofillResult()
    tried: set[str] = set()
    new_skus: set[str] = set()
    start_skus = {l.sku for l in plan.lines}
    for _ in range(max_steps):
        ev = evaluate(plan, products, predictor, stock, capacity_left_m3)
        res.final = ev
        anchor = ev.anchor_fc
        if not anchor or anchor not in ev.groups:
            res.stopped_because = "brak magazynu głównego"
            break
        g = ev.groups[anchor]
        has_dims = bool(g.pallets) and g.pack.total_volume_cm3 > 0
        last = g.pallets[-1] if g.pallets else None
        if plan.mode == "pallet" and has_dims:
            if len(g.pallets) > plan.max_pallets:
                res.stopped_because = f"przekroczono limit {plan.max_pallets} palet"
                break
            if len(g.pallets) == plan.max_pallets and last.fill_ratio >= target_fill:
                res.stopped_because = f"osiągnięto wypełnienie {last.fill_ratio:.0%}"
                break
        elif g.units >= target_units:
            res.stopped_because = f"osiągnięto {g.units} szt. (cel {target_units})"
            break
        if capacity_left_m3 is not None and ev.volume_m3 >= capacity_left_m3:
            res.stopped_because = "wyczerpany limit pojemności"
            break

        pick_sku: Optional[str] = None
        qty = 0
        # 1) new filler products (diversity first)
        if len(new_skus) < max_new_skus:
            cands = suggest(ev, products, predictor, stock, stats, weights, exclude=tried)
            cands = [c for c in cands if c.qty > 0 and not c.problems and (c.fits_cartons is None or c.fits_cartons > 0)]
            if cands:
                c = cands[0]
                pick_sku, qty = c.sku, c.qty
                new_skus.add(c.sku)
        # 2) top up products already in the plan and routed to the anchor FC
        if pick_sku is None:
            tops = []
            for le in g.lines:
                sku = le.line.sku
                p = products.get(sku)
                if p is None or sku in tried or not le.prediction.fc == anchor:
                    continue
                upc = p.units_per_carton
                room = _room_left(sku, plan.qty_of(sku), products, stock)
                if room < upc:
                    continue
                if has_dims and last is not None:
                    c = carton_for(p, upc)
                    fp = c.footprint()
                    if c.dims is None or fp is None or last.room_for(fp, c.height, c.weight_kg or 0.0) <= 0:
                        continue
                tops.append((_velocity(sku, stock, stats), -g.lines.index(le), sku, upc))
            if tops:
                tops.sort(reverse=True)
                _, _, pick_sku, qty = tops[0]
        if pick_sku is None:
            res.stopped_because = "brak dalszych kandydatów (produkty tego magazynu, mieszczące się na palecie)"
            break

        before = plan.qty_of(pick_sku)
        for l in plan.lines:
            if l.sku == pick_sku:
                l.qty += qty
                break
        else:
            plan.lines.append(PlanLine(pick_sku, qty))
        ev2 = evaluate(plan, products, predictor, stock, capacity_left_m3)
        g2 = ev2.groups.get(anchor)
        overflow = plan.mode == "pallet" and has_dims and g2 is not None and len(g2.pallets) > plan.max_pallets
        if overflow or (capacity_left_m3 is not None and ev2.volume_m3 > capacity_left_m3):
            for l in plan.lines:
                if l.sku == pick_sku:
                    l.qty = before
            plan.lines = [l for l in plan.lines if l.qty > 0]
            tried.add(pick_sku)
            if pick_sku not in start_skus and before == 0:
                new_skus.discard(pick_sku)
            continue
        res.added.append((pick_sku, qty))
    else:
        res.stopped_because = "limit kroków"
    res.final = evaluate(plan, products, predictor, stock, capacity_left_m3)
    return res
