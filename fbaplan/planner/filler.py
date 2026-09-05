"""Filler recommender: which products (and how many) to add to a plan so that
the pallet / cartons to the anchor FC fill up, without triggering a split."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from ..history.store import HistoryStats
from ..models import Plan, Product, StockRow
from ..packing.fill import carton_for
from ..predict.fc import FCPredictor
from .session import PlanEval

DEFAULT_WEIGHTS = {
    "w_fc": 3.0,        # probability that the product goes to the anchor FC
    "w_sales": 1.5,     # sales velocity (normalised to the best candidate)
    "w_stock": 2.0,     # low FBA cover (1 - cover/target)
    "w_fit": 1.0,       # closes a pallet layer / fits remaining space
    "w_affinity": 0.5,  # historically shipped together with the anchor products
    "min_fc_prob": 0.8,
    "target_cover_days": 60,
    "max_suggestions": 25,
    "default_qty_cartons": 1,
}


@dataclass
class Suggestion:
    sku: str
    name: str
    qty: int
    cartons: int
    fc: str
    p_fc: float
    fc_source: str
    velocity_month: float
    cover_days: Optional[float]
    fits_cartons: Optional[int]     # how many cartons of this product still fit on the last pallet
    affinity: float
    score: float
    reasons: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _units_month(stock: Optional[StockRow], hist_units_12m: int) -> float:
    if stock and (stock.sales_30d or stock.sales_90d):
        return stock.daily_velocity * 30.0
    return hist_units_12m / 12.0


def suggest(ev: PlanEval, products: dict[str, Product], predictor: FCPredictor,
            stock: Optional[dict[str, StockRow]] = None, stats: Optional[HistoryStats] = None,
            weights: Optional[dict] = None, exclude: Iterable[str] = ()) -> list[Suggestion]:
    W = dict(DEFAULT_WEIGHTS)
    if weights:
        W.update(weights)
    plan: Plan = ev.plan
    anchor = ev.anchor_fc
    if not anchor:
        return []
    in_plan = {l.sku for l in plan.lines}
    excluded = set(exclude) | set(plan.excluded_skus)
    anchor_groups = {products[s].pack_group for s in in_plan if s in products and products[s].pack_group}
    group = ev.groups.get(anchor)
    last_pallet = group.pallets[-1] if group and group.pallets else None
    stock = stock or {}

    cands: list[Suggestion] = []
    for sku, p in products.items():
        if sku in in_plan or sku in excluded or not p.active:
            continue
        pred = predictor.predict(p)
        p_fc = pred.prob(anchor)
        if not pred.fc or p_fc < W["min_fc_prob"]:
            continue
        problems: list[str] = []
        if anchor_groups and p.pack_group and p.pack_group not in anchor_groups:
            problems.append(f"inna grupa pakowania ({p.pack_group})")
        st = stock.get(sku)
        hs = stats.by_sku.get(sku) if stats else None
        vel = _units_month(st, hs.units_12m if hs else 0)
        cover = st.cover_days if st else None
        carton = carton_for(p, p.units_per_carton)
        fits: Optional[int] = None
        if last_pallet is not None and carton.dims is not None:
            fp = carton.footprint()
            fits = last_pallet.room_for(fp, carton.height, carton.weight_kg or 0.0) if fp else None
        aff = 0.0
        if stats:
            vals = [stats.affinity(sku, a) for a in in_plan]
            aff = max(vals) if vals else 0.0
        qty_cartons = int(W["default_qty_cartons"])
        if fits is not None:
            qty_cartons = max(1, min(qty_cartons if fits >= qty_cartons else fits, fits)) if fits > 0 else 0
        if p.max_qty_per_plan:
            qty_cartons = min(qty_cartons, max(0, p.max_qty_per_plan // p.units_per_carton))
        if st and st.local_stock is not None:
            qty_cartons = min(qty_cartons, max(0, st.local_stock // p.units_per_carton))
        qty = qty_cartons * p.units_per_carton
        reasons = [f"{anchor}: {p_fc:.0%} ({pred.source})"]
        if vel:
            reasons.append(f"sprzedaż ≈ {vel:.0f} szt./mies.")
        if cover is not None:
            reasons.append(f"zapas FBA na {cover:.0f} dni")
        if fits is not None:
            reasons.append(f"na ostatnią paletę wejdzie jeszcze {fits} kart.")
        if aff > 1.2:
            reasons.append(f"często wysyłany razem (lift {aff:.1f})")
        cands.append(Suggestion(sku, p.name, qty, qty_cartons, pred.fc, p_fc, pred.source, vel, cover, fits, aff, 0.0, reasons, problems))

    if not cands:
        return []
    max_vel = max(c.velocity_month for c in cands) or 1.0
    max_aff = max(c.affinity for c in cands) or 1.0
    target = float(W["target_cover_days"])
    for c in cands:
        s_fc = c.p_fc
        s_sales = c.velocity_month / max_vel
        s_stock = 0.5 if c.cover_days is None else max(0.0, 1.0 - c.cover_days / target)
        if c.cover_days is None and c.velocity_month == 0:
            s_stock = 0.0
        s_fit = 0.0 if c.fits_cartons is None else (1.0 if c.fits_cartons > 0 else -1.0)
        s_aff = c.affinity / max_aff
        c.score = W["w_fc"] * s_fc + W["w_sales"] * s_sales + W["w_stock"] * s_stock + W["w_fit"] * s_fit + W["w_affinity"] * s_aff
        if c.problems:
            c.score -= 2.0
        if c.qty == 0:
            c.score -= 3.0
    cands.sort(key=lambda c: -c.score)
    return cands[: int(W["max_suggestions"])]
