"""Evaluate a plan: predicted FC split, cartons, pallets, utilisation, warnings."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..models import Plan, PlanLine, Product, StockRow
from ..packing.fill import Carton, PackResult, PalletLoad, pack_pallets, plan_cartons, volume_m3
from ..predict.fc import FCPrediction, FCPredictor
from ..rules import amazon as A


@dataclass
class LineEval:
    line: PlanLine
    product: Optional[Product]
    prediction: FCPrediction
    cartons: list[Carton]
    problems: list[str] = field(default_factory=list)

    @property
    def qty(self) -> int:
        return self.line.qty

    @property
    def full_cartons(self) -> int:
        return sum(1 for c in self.cartons if c.full)

    @property
    def partial_units(self) -> int:
        return sum(c.units for c in self.cartons if not c.full)

    @property
    def volume_m3(self) -> float:
        return volume_m3(self.cartons)


@dataclass
class FCGroup:
    fc: str
    lines: list[LineEval]
    pack: PackResult

    @property
    def units(self) -> int:
        return sum(l.qty for l in self.lines)

    @property
    def cartons(self) -> int:
        return len(self.pack.all_cartons)

    @property
    def volume_m3(self) -> float:
        return self.pack.total_volume_cm3 / 1e6

    @property
    def weight_kg(self) -> float:
        return self.pack.total_weight_kg

    @property
    def pallets(self) -> list[PalletLoad]:
        return self.pack.pallets

    @property
    def fill_ratio(self) -> float:
        """Utilisation of the LAST pallet (the one that can still be filled)."""
        return self.pack.pallets[-1].fill_ratio if self.pack.pallets else 0.0

    @property
    def total_fill_ratio(self) -> float:
        if not self.pack.pallets:
            return 0.0
        return self.pack.total_volume_cm3 / (len(self.pack.pallets) * self.pack.pallets[0].volume_capacity_cm3)


@dataclass
class PlanEval:
    plan: Plan
    lines: list[LineEval]
    groups: dict[str, FCGroup]
    warnings: list[str]
    anchor_fc: str
    capacity_left_m3: Optional[float] = None

    @property
    def units(self) -> int:
        return sum(l.qty for l in self.lines)

    @property
    def volume_m3(self) -> float:
        return sum(g.volume_m3 for g in self.groups.values())

    @property
    def split(self) -> bool:
        return len([g for g in self.groups.values() if g.fc]) > 1

    def minority_lines(self) -> list[LineEval]:
        return [l for l in self.lines if l.prediction.fc and l.prediction.fc != self.anchor_fc]

    def cost_per_unit(self, pallet_rate: Optional[float], parcel_rate: Optional[float]) -> dict[str, Optional[float]]:
        """Indicative freight cost per unit per FC group (rates in PLN)."""
        out: dict[str, Optional[float]] = {}
        for fc, g in self.groups.items():
            if self.plan.mode == "pallet" and pallet_rate:
                cost = pallet_rate * max(1, len(g.pallets))
            elif self.plan.mode == "parcel" and parcel_rate:
                cost = parcel_rate * max(1, g.cartons)
            else:
                out[fc] = None
                continue
            out[fc] = cost / g.units if g.units else None
        return out


def evaluate(plan: Plan, products: dict[str, Product], predictor: FCPredictor,
             stock: Optional[dict[str, StockRow]] = None, capacity_left_m3: Optional[float] = None,
             allow_partial_cartons: bool = True) -> PlanEval:
    """Evaluate a plan end-to-end."""
    line_evals: list[LineEval] = []
    warnings: list[str] = []
    for line in plan.lines:
        p = products.get(line.sku)
        pred = predictor.predict(p, sku=line.sku, name=line.sku if p is None else p.name)
        cartons = plan_cartons(products, [(line.sku, line.qty)], allow_partial=allow_partial_cartons) if p else []
        problems: list[str] = []
        if p is None:
            problems.append("SKU nie ma w katalogu")
        else:
            if not p.active:
                problems.append("produkt nieaktywny")
            if p.max_qty_per_plan and line.qty > p.max_qty_per_plan:
                problems.append(f"ilość {line.qty} > limit {p.max_qty_per_plan}/plan")
            if p.units_per_carton > 1 and line.qty % p.units_per_carton:
                problems.append(f"{line.qty % p.units_per_carton} szt. poza pełnym kartonem (karton = {p.units_per_carton})")
            if p.unit_dims is None and (p.carton is None or p.carton.dims is None):
                problems.append("brak wymiarów — nie policzę objętości")
            if stock is not None and line.sku in stock and stock[line.sku].local_stock is not None and line.qty > stock[line.sku].local_stock:
                problems.append(f"ilość {line.qty} > stan własny {stock[line.sku].local_stock}")
        if pred.source == "unknown":
            problems.append("nie umiem przewidzieć magazynu")
        line_evals.append(LineEval(line, p, pred, cartons, problems))

    # anchor FC: explicit target, else the FC that takes most pallet space (volume; qty as
    # fallback when dimensions are unknown), first line wins ties — the main product decides
    votes: dict[str, float] = {}
    order: dict[str, int] = {}
    for i, le in enumerate(line_evals):
        fc = le.prediction.fc
        if not fc:
            continue
        vol = sum(c.volume_cm3 for c in le.cartons)
        weight = vol if vol > 0 else le.qty * 1000.0
        votes[fc] = votes.get(fc, 0.0) + weight * max(le.prediction.confidence, 0.05)
        order.setdefault(fc, i)
    anchor = plan.target_fc or (max(votes, key=lambda f: (votes[f], -order[f])) if votes else "")

    groups: dict[str, FCGroup] = {}
    for fc in sorted({le.prediction.fc for le in line_evals}):
        ls = [le for le in line_evals if le.prediction.fc == fc]
        cartons = [c for le in ls for c in le.cartons]
        pack = pack_pallets(cartons, max_pallets=plan.max_pallets if fc == anchor else 0)
        groups[fc or "?"] = FCGroup(fc or "?", ls, pack)

    # warnings
    fcs = [fc for fc in groups if fc != "?"]
    if len(fcs) > 1:
        minority = [le for le in line_evals if le.prediction.fc and le.prediction.fc != anchor]
        warnings.append(
            f"Plan zostanie prawdopodobnie podzielony na {len(fcs)} magazyny ({', '.join(fcs)}); "
            f"poza {anchor}: {len(minority)} pozycji, {sum(l.qty for l in minority)} szt."
        )
    if "?" in groups:
        warnings.append(f"{len(groups['?'].lines)} pozycji bez przewidywanego magazynu")
    low_conf = [le for le in line_evals if le.prediction.fc and le.prediction.confidence < 0.5]
    if low_conf:
        warnings.append("Niska pewność przewidywania dla: " + ", ".join(le.line.sku for le in low_conf))
    for fc, g in groups.items():
        for i in g.pack.issues:
            warnings.append(f"{fc}: {i}")
    for le in line_evals:
        for pr in le.problems:
            warnings.append(f"{le.line.sku}: {pr}")
    total_vol = sum(g.volume_m3 for g in groups.values())
    if capacity_left_m3 is not None and total_vol > capacity_left_m3:
        warnings.append(f"Objętość planu {total_vol:.2f} m³ przekracza wolny limit pojemności {capacity_left_m3:.2f} m³")
    if plan.mode == "pallet" and anchor in groups:
        g = groups[anchor]
        if len(g.pallets) > plan.max_pallets:
            warnings.append(f"{anchor}: {len(g.pallets)} palet, limit planu {plan.max_pallets}")
    return PlanEval(plan, line_evals, groups, warnings, anchor, capacity_left_m3)


def apply_verdict(plan: Plan, verdict: dict[str, str], when: str) -> list[dict]:
    """Record Amazon's actual FC per SKU; return verdict rows for verdicts.csv."""
    rows = []
    plan.verdicts = dict(verdict)
    plan.verdict_date = when
    plan.status = "verdict"
    for sku, fc in verdict.items():
        if not fc:
            continue
        rows.append({"date": when, "plan_id": plan.plan_id, "sku": sku, "fc": fc, "qty": plan.qty_of(sku), "shipment_id": "", "note": ""})
    return rows


def verdict_diff(ev: PlanEval, verdict: dict[str, str]) -> list[tuple[str, str, str]]:
    """(sku, predicted, actual) for lines where Amazon decided differently than predicted."""
    out = []
    for le in ev.lines:
        actual = verdict.get(le.line.sku, "")
        if actual and actual != le.prediction.fc:
            out.append((le.line.sku, le.prediction.fc, actual))
    return out
