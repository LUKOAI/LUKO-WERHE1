from datetime import date

from fbaplan.history.store import compute_stats
from fbaplan.models import CartonSpec, Dims, HistoryLine, Plan, PlanLine, Product, StockRow
from fbaplan.planner.filler import suggest
from fbaplan.planner.session import apply_verdict, evaluate, verdict_diff
from fbaplan.predict.fc import FCPredictor


def _catalog():
    return {
        "1WG80x800p": Product("1WG80x800p", "Świder 80x800 SDS Plus", "auger", unit_dims=Dims(82, 10, 10), unit_weight_kg=3.0,
                              carton=CartonSpec(4, Dims(84, 22, 22), 12.5), pack_group="dlugie"),
        "1WG100x800p": Product("1WG100x800p", "Świder 100x800 SDS Plus", "auger", unit_dims=Dims(82, 12, 12), unit_weight_kg=3.6,
                               carton=CartonSpec(4, Dims(84, 26, 26), 15.0), pack_group="dlugie"),
        "3DB75x600m": Product("3DB75x600m", "Dłuto 75x600 SDS Max", "chisel_flat", unit_dims=Dims(61, 8, 4), unit_weight_kg=2.0,
                              carton=CartonSpec(10, Dims(63, 30, 20), 20.5), pack_group="dlugie"),
        "4APlus": Product("4APlus", "Adapter SDS Plus", "adapter", unit_dims=Dims(12, 5, 5), unit_weight_kg=0.2,
                          carton=CartonSpec(50, Dims(40, 30, 20), 10.5), pack_group="male"),
        "7NT744D": Product("7NT744D", "Nożyki T744D 5 szt.", "blade_jigsaw", unit_dims=Dims(20, 5, 1), unit_weight_kg=0.1,
                           carton=CartonSpec(100, Dims(40, 30, 20), 10.5), pack_group="male"),
        "NODIMS": Product("NODIMS", "Świder 60x600 bez wymiarów", "auger", carton=CartonSpec(6)),
    }


def _history():
    h = []
    for _ in range(6):
        h.append(HistoryLine("1WG80x800p", "XPO1", date(2026, 4, 1), 20, "FBA1", "pallet"))
        h.append(HistoryLine("1WG100x800p", "XPO1", date(2026, 4, 1), 12, "FBA1", "pallet"))
        h.append(HistoryLine("4APlus", "WRO5", date(2026, 5, 1), 100, "FBA2", "parcel"))
        h.append(HistoryLine("7NT744D", "WRO5", date(2026, 5, 1), 100, "FBA2", "parcel"))
    h.append(HistoryLine("3DB75x600m", "XPO1", date(2026, 6, 1), 10, "FBA3"))
    return h


def test_evaluate_split_and_fill():
    cat, hist = _catalog(), _history()
    pr = FCPredictor(hist, as_of=date(2026, 9, 1))
    plan = Plan("P1", "2026-09-01T10:00:00", mode="pallet", max_pallets=1)
    plan.lines = [PlanLine("1WG80x800p", 40), PlanLine("4APlus", 50), PlanLine("NODIMS", 7)]
    ev = evaluate(plan, cat, pr)
    assert ev.anchor_fc == "XPO1"
    assert ev.split and set(ev.groups) == {"XPO1", "WRO5"}
    assert any("podzielony" in w for w in ev.warnings)
    g = ev.groups["XPO1"]
    assert g.units == 47 and len(g.pallets) == 1
    assert 0 < g.fill_ratio < 1
    assert any("NODIMS" in w and "wymiar" in w for w in ev.warnings)
    assert any("4APlus" in l.line.sku for l in ev.minority_lines())
    # NODIMS predicted by family rule (auger -> XPO1), cartons without dims are unplaceable
    nod = next(l for l in ev.lines if l.line.sku == "NODIMS")
    assert nod.prediction.fc == "XPO1" and nod.prediction.source == "rule_name"
    assert any("7 szt. poza pełnym kartonem" not in p and "poza pełnym kartonem" in p for p in nod.problems)


def test_suggest_fillers_same_fc():
    cat, hist = _catalog(), _history()
    pr = FCPredictor(hist, as_of=date(2026, 9, 1))
    stats = compute_stats(hist, as_of=date(2026, 9, 1))
    stock = {"1WG100x800p": StockRow("1WG100x800p", fba_available=5, sales_30d=60),
             "3DB75x600m": StockRow("3DB75x600m", fba_available=500, sales_30d=10),
             "4APlus": StockRow("4APlus", fba_available=0, sales_30d=300)}
    plan = Plan("P2", "2026-09-01T10:00:00", mode="pallet", max_pallets=1)
    plan.lines = [PlanLine("1WG80x800p", 40)]
    ev = evaluate(plan, cat, pr)
    sugg = suggest(ev, cat, pr, stock=stock, stats=stats)
    skus = [s.sku for s in sugg]
    assert "4APlus" not in skus  # goes to WRO5
    assert skus[0] == "1WG100x800p"  # low cover, sells, same FC, shipped together
    top = sugg[0]
    assert top.qty % 4 == 0 and top.qty > 0
    assert top.fits_cartons is not None and top.fits_cartons > 0
    assert top.affinity > 1.0
    # low-stock, slow seller with high cover ranks lower
    assert skus.index("3DB75x600m") > 0


def test_verdict_updates_predictor():
    cat, hist = _catalog(), _history()
    pr = FCPredictor(hist, as_of=date(2026, 9, 1))
    plan = Plan("P3", "2026-09-01T10:00:00")
    plan.lines = [PlanLine("3DB75x600m", 20)]
    ev = evaluate(plan, cat, pr)
    assert ev.lines[0].prediction.fc == "XPO1"
    rows = apply_verdict(plan, {"3DB75x600m": "WRO5"}, "2026-09-02")
    assert plan.status == "verdict" and rows[0]["fc"] == "WRO5"
    assert verdict_diff(ev, plan.verdicts) == [("3DB75x600m", "XPO1", "WRO5")]
    for r in rows:
        pr.add(HistoryLine(r["sku"], r["fc"], date.fromisoformat(r["date"]), r["qty"], source="verdict"))
    again = pr.predict(cat["3DB75x600m"])
    assert again.probs["WRO5"] > again.probs["XPO1"]
