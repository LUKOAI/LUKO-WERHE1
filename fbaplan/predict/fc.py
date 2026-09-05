"""FC predictor: which fulfilment centre will Amazon route a SKU to?

Three sources, in order of trust:

1. manual override on the product (``fc_override``),
2. history (imported shipments + recorded Amazon verdicts) with recency
   weighting, restricted to the current FC regime (Polish FCs since 06.2024),
3. physical rule: the longest side of the packaged unit decides —
   ≥ 460 mm -> non-sortable (XPO1), < 400 mm -> sortable (WRO5), 400-459 mm
   is a grey zone decided by sub-rules learned from history (accuracy of the
   full rule on 2024-06..2026-08 history: 99.3 % of lines, see
   docs/analiza/fc_rules.md). Dimensions come from the catalog when known,
   otherwise the length is estimated from the product name.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from ..catalog.normalize import Features, estimate_length_mm, extract
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
    "threshold_mm": 460,                # longest side >= this -> non-sortable
    "gray_lo_mm": 400,                  # 400..459 mm: grey zone (per-ASIN packaging decides)
    "gray_zone_p_nonsortable": 0.63,    # base rate in the grey zone when no sub-rule matches
}


@dataclass
class FCPrediction:
    sku: str
    probs: dict[str, float]
    fc: str
    confidence: float           # 0..1
    source: str                 # override | history | rule_dims | rule_name | ...+history | unknown
    evidence: dict = field(default_factory=dict)
    explanation: str = ""
    uncertain: bool = False     # grey-zone product without history: do not use as filler

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
        """Size-tier rule from catalog dimensions (standard size -> sortable)."""
        std = A.is_standard_size(product.unit_dims, product.unit_weight_kg)
        if std is None:
            return None
        return self.params["sortable_fc"] if std else self.params["nonsortable_fc"]

    def rule_from_name(self, name: str, family: str = "") -> tuple[Optional[str], Features, bool, str]:
        """Length rule with grey-zone sub-rules. Returns (fc, features, certain, why)."""
        S, N = self.params["sortable_fc"], self.params["nonsortable_fc"]
        ft = extract(name or "")
        fam = (family if family and family != "other" else ft.family) or ""
        L, is_default = estimate_length_mm(name or "", ft)
        n = (name or "").lower()
        thr, lo = float(self.params["threshold_mm"]), float(self.params["gray_lo_mm"])
        if is_default and fam in ("", "other"):
            return None, ft, False, "nierozpoznana rodzina produktu i brak wymiaru"
        if L is None:
            if fam in ("auger", "handle"):
                return N, ft, False, f"rodzina „{fam}” bez wymiaru → domyślnie {N}"
            if fam:
                return S, ft, False, f"rodzina „{fam}” bez wymiaru → domyślnie {S}"
            return None, ft, False, "nierozpoznana rodzina i brak wymiaru"
        src = "długość domyślna dla rodziny" if is_default else "długość z nazwy"
        if L >= thr:
            return N, ft, not is_default, f"{src} {L:g} mm ≥ {thr:g} → {N}"
        if L < lo:
            return S, ft, not is_default, f"{src} {L:g} mm < {lo:g} → {S}"
        # grey zone 400–459 mm: packaging registered per ASIN decides; sub-rules from history
        d = ft.diameter_mm
        if fam in ("blade_recip", "blade_jigsaw"):
            return S, ft, True, f"brzeszczot {L:g} mm → {S}"
        if fam == "extension" or "przedłuż" in n or "przedluz" in n or "słupek" in n:
            return S, ft, True, f"przedłużka {L:g} mm → {S}"
        if fam.startswith("chisel") and d and d >= 105:
            return N, ft, True, f"szerokie dłuto/szypa {d:g}×{L:g} mm (walizka) → {N}"
        if ft.shank == "hex28":
            return S, ft, True, f"dłuto HEX28 {L:g} mm → {S}"
        if fam == "auger":
            if d == 80:
                return S, ft, True, f"świder 80×{L:g} → {S} (wyjątek per ASIN)"
            return N, ft, True, f"świder {L:g} mm → {N}"
        if fam in ("chisel_spade", "chisel_flat") and ft.shank == "hex30" and d == 75:
            return S, ft, True, f"szpadel 75×{L:g} HEX30 → {S}"
        return N, ft, False, f"szara strefa {L:g} mm (dłuta SDS 400–410, HEX30 410, zestawy) → zwykle {N}, niepewne"

    # -- main --------------------------------------------------------------- #
    def predict(self, product: Optional[Product], sku: str = "", name: str = "") -> FCPrediction:
        sku = sku or (product.sku if product else "")
        name = name or (product.name if product else "")
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

        # rule (dims from catalog, else name) + weak history blended in
        rule_fc = self.rule_from_dims(product) if product else None
        certain, why = True, ""
        if rule_fc is not None and product is not None:
            src = "rule_dims"
            tier = A.size_tier(product.unit_dims, product.unit_weight_kg)
            why = f"wymiary {product.unit_dims.longest:.0f} cm / {product.unit_weight_kg or 0:.2f} kg → klasa „{tier.name_pl if tier else '?'}” → {rule_fc}"
        else:
            src = "rule_name"
            rule_fc, _ft, certain, why = self.rule_from_name(name, product.family if product else "")
        if rule_fc is None and not probs:
            return FCPrediction(sku, {}, "", 0.0, "unknown", ev, "brak historii, wymiarów i rozpoznanej rodziny produktu")

        S, N = self.params["sortable_fc"], self.params["nonsortable_fc"]
        if rule_fc:
            p_rule = 0.9 if certain else float(self.params["gray_zone_p_nonsortable"])
            other = S if rule_fc == N else N
            rp = {rule_fc: p_rule, other: 1.0 - p_rule}
        else:
            rp = {}
        if probs:
            a = min(1.0, total / min_w) * 0.6
            keys = set(rp) | set(probs)
            blended = {k: (1 - a) * rp.get(k, 0.0) + a * probs.get(k, 0.0) for k in keys}
            fc = max(blended, key=blended.get)
            conf = blended[fc] * 0.7
            expl = f"reguła: {why}; słaba historia ({ev['lines']} wysyłek) → mieszane"
            return FCPrediction(sku, blended, fc, conf, src + "+history", ev, expl, uncertain=not certain and conf < 0.6)
        conf = (0.8 if src == "rule_dims" else 0.7) if certain else 0.4
        return FCPrediction(sku, rp, rule_fc or "", conf, src, ev, why, uncertain=not certain)

    def predict_many(self, products: dict[str, Product], skus: Iterable[str]) -> dict[str, FCPrediction]:
        return {s: self.predict(products.get(s), sku=s) for s in skus}
