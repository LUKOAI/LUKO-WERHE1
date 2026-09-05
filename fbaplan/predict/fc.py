"""FC predictor: which fulfilment centre will Amazon route a SKU to?

Three sources, in order of trust:

1. manual override on the product (``fc_override``),
2. history (imported shipments + recorded Amazon verdicts) with recency
   weighting, restricted to the current FC regime,
3. physical rule: standard-size units -> sortable FC (WRO5), oversize units ->
   non-sortable FC (XPO1); when no dimensions are known, a family/length rule
   derived from the product name.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from ..catalog.normalize import Features, extract
from ..models import HistoryLine, Product
from ..rules import amazon as A

DEFAULT_PARAMS = {
    "regime_start": "2024-06-01",       # only evidence from this date on
    "half_life_months": 12.0,           # weight = 0.5 ** (months_ago / half_life)
    "min_weight": 1.5,                  # minimum total weight to trust history (≈ 3 lines a year old)
    "sortable_fc": "WRO5",
    "nonsortable_fc": "XPO1",
    "known_fcs": ["WRO5", "XPO1"],
    "verdict_weight": 2.0,              # a recorded verdict counts as this many history lines
    # family rule when dimensions are unknown: family -> (fc, threshold on length_mm or None)
    "family_rule": {
        "auger": ["XPO1", None], "set_chisel": ["XPO1", None], "set_drill": ["XPO1", None],
        "chisel_flat": ["XPO1", 450], "chisel_point": ["XPO1", 450], "chisel_spade": ["XPO1", 450],
        "chisel_gouge": ["XPO1", 450], "chisel_bush": ["WRO5", None], "drill_bit": ["WRO5", 450],
        "extension": ["WRO5", 450], "driver_rod": ["WRO5", None], "driver_pile": ["WRO5", None],
        "tamper": ["WRO5", None], "adapter": ["WRO5", None], "set_adapter": ["WRO5", None],
        "blade_jigsaw": ["WRO5", None], "blade_recip": ["WRO5", None], "saw_disc": ["WRO5", None],
        "grease": ["WRO5", None], "hole_saw": ["WRO5", None], "pin": ["WRO5", None],
        "handle": ["WRO5", None], "spring": ["WRO5", None], "string": ["WRO5", None],
    },
    "length_threshold_mm": 450,         # longest side above this -> non-sortable (used with family rule)
}


@dataclass
class FCPrediction:
    sku: str
    probs: dict[str, float]
    fc: str
    confidence: float           # 0..1
    source: str                 # override | history | rule_dims | rule_family | unknown
    evidence: dict = field(default_factory=dict)
    explanation: str = ""

    def prob(self, fc: str) -> float:
        return self.probs.get(fc, 0.0)


def _months_between(a: date, b: date) -> float:
    return (b.year - a.year) * 12 + (b.month - a.month) + (b.day - a.day) / 30.0


class FCPredictor:
    def __init__(self, history: Iterable[HistoryLine] = (), params: Optional[dict] = None, as_of: Optional[date] = None):
        self.params = dict(DEFAULT_PARAMS)
        if params:
            self.params.update(params)
        self.as_of = as_of or date.today()
        self._by_sku: dict[str, list[HistoryLine]] = {}
        for h in history:
            self.add(h)

    # -- evidence ----------------------------------------------------------- #
    def add(self, h: HistoryLine) -> None:
        if not h.sku or not h.fc:
            return
        self._by_sku.setdefault(h.sku, []).append(h)

    def evidence_for(self, sku: str) -> list[HistoryLine]:
        return self._by_sku.get(sku, [])

    def _history_probs(self, sku: str) -> tuple[dict[str, float], float, dict]:
        start = date.fromisoformat(self.params["regime_start"])
        hl = float(self.params["half_life_months"])
        w: dict[str, float] = {}
        n = 0
        last: Optional[date] = None
        for h in self._by_sku.get(sku, []):
            if h.when < start:
                continue
            months = max(0.0, _months_between(h.when, self.as_of))
            weight = 0.5 ** (months / hl)
            if h.source == "verdict":
                weight *= float(self.params["verdict_weight"])
            w[h.fc] = w.get(h.fc, 0.0) + weight
            n += 1
            last = h.when if last is None or h.when > last else last
        total = sum(w.values())
        probs = {k: v / total for k, v in w.items()} if total else {}
        return probs, total, {"lines": n, "last": last.isoformat() if last else None, "weights": {k: round(v, 2) for k, v in w.items()}}

    # -- rules -------------------------------------------------------------- #
    def rule_from_dims(self, product: Product) -> Optional[str]:
        std = A.is_standard_size(product.unit_dims, product.unit_weight_kg)
        if std is None:
            return None
        return self.params["sortable_fc"] if std else self.params["nonsortable_fc"]

    def rule_from_name(self, name: str, family: str = "") -> tuple[Optional[str], Features]:
        ft = extract(name or "")
        fam = family or ft.family
        rule = self.params["family_rule"].get(fam)
        if not rule:
            return None, ft
        fc, thr = rule
        if thr is not None and ft.length_mm:
            thr_len = float(self.params.get("length_threshold_mm", thr))
            return (self.params["nonsortable_fc"] if ft.length_mm >= thr_len else self.params["sortable_fc"]), ft
        return fc, ft

    # -- main --------------------------------------------------------------- #
    def predict(self, product: Optional[Product], sku: str = "", name: str = "") -> FCPrediction:
        sku = sku or (product.sku if product else "")
        name = name or (product.name if product else "")
        known = list(self.params["known_fcs"])
        if product and product.fc_override:
            fc = product.fc_override
            return FCPrediction(sku, {fc: 1.0}, fc, 1.0, "override", {}, f"ręczne przypisanie do {fc}")

        probs, total, ev = self._history_probs(sku)
        min_w = float(self.params["min_weight"])
        if probs and total >= min_w:
            fc = max(probs, key=probs.get)
            conf = probs[fc] * min(1.0, total / (3 * min_w))
            expl = f"historia: {ev['lines']} wysyłek od {self.params['regime_start'][:7]}, ostatnia {ev['last']}, udział {fc} = {probs[fc]:.0%}"
            return FCPrediction(sku, probs, fc, conf, "history", ev, expl)

        # weak history + rule: blend
        rule_fc = self.rule_from_dims(product) if product else None
        src = "rule_dims"
        ft = None
        if rule_fc is None:
            rule_fc, ft = self.rule_from_name(name, product.family if product else "")
            src = "rule_family"
        if rule_fc is None and not probs:
            return FCPrediction(sku, {}, "", 0.0, "unknown", ev, "brak historii, wymiarów i rozpoznanej rodziny produktu")

        rp = {rule_fc: 1.0} if rule_fc else {}
        if probs:
            # history has some weight; blend proportionally
            a = min(1.0, total / min_w) * 0.6
            keys = set(rp) | set(probs)
            blended = {k: (1 - a) * rp.get(k, 0.0) + a * probs.get(k, 0.0) for k in keys}
            fc = max(blended, key=blended.get)
            conf = blended[fc] * 0.7
            expl = f"reguła ({'wymiary' if src == 'rule_dims' else 'rodzina'}) → {rule_fc or '?'}, słaba historia ({ev['lines']} wysyłek) → mieszane"
            return FCPrediction(sku, blended, fc, conf, src + "+history", ev, expl)
        conf = 0.75 if src == "rule_dims" else 0.6
        if src == "rule_dims" and product is not None:
            tier = A.size_tier(product.unit_dims, product.unit_weight_kg)
            expl = f"wymiary {product.unit_dims.longest:.0f} cm / {product.unit_weight_kg or 0:.2f} kg → klasa „{tier.name_pl if tier else '?'}” → {rule_fc}"
        else:
            expl = f"rodzina „{(ft.family if ft else '?')}”" + (f", długość {ft.length_mm} mm" if ft and ft.length_mm else "") + f" → {rule_fc}"
        return FCPrediction(sku, rp, rule_fc or "", conf, src, ev, expl)

    def predict_many(self, products: dict[str, Product], skus: Iterable[str]) -> dict[str, FCPrediction]:
        return {s: self.predict(products.get(s), sku=s) for s in skus}
