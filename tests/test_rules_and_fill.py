from datetime import date

from fbaplan.models import CartonSpec, Dims, HistoryLine, Product
from fbaplan.packing.fill import (
    carton_for, cartons_for_line, estimate_carton_dims, pack_pallets, per_layer_capacity, plan_cartons,
)
from fbaplan.predict.fc import FCPredictor
from fbaplan.rules import amazon as A


def test_size_tiers():
    assert A.size_tier(Dims(30, 20, 2), 0.05).code == "light_envelope"
    assert A.size_tier(Dims(40, 30, 20), 5.0).code == "standard_parcel"
    # 80 cm auger: oversize
    t = A.size_tier(Dims(80, 12, 12), 2.5)
    assert t.code == "standard_oversize" and not t.standard_size
    # 41 cm chisel, 1.3 kg: standard parcel (sortable)
    assert A.is_standard_size(Dims(42, 8, 4), 1.3) is True
    # 46 cm long -> not standard
    assert A.is_standard_size(Dims(46, 8, 4), 1.3) is False
    assert A.size_tier(Dims(200, 20, 20), 5).code == "special_oversize"
    assert A.size_tier(None, 1.0) is None


def test_box_validation():
    assert A.validate_box(Dims(60, 40, 30), 12) == []
    assert any("63.5" in s or "63,5" in s for s in A.validate_box(Dims(90, 20, 20), 10))
    assert A.validate_box(Dims(90, 20, 20), 10, single_oversize_unit=True) == []
    assert any("23" in s for s in A.validate_box(Dims(40, 40, 40), 24))
    assert any("ciężka" in s for s in A.validate_box(Dims(40, 40, 40), 16))


def test_estimate_carton_dims():
    d = estimate_carton_dims(Dims(41, 8, 4), 10)
    assert d.longest < 63.5
    assert d.volume_cm3 >= 10 * 41 * 8 * 4


def test_cartons_for_line_and_pallet():
    p = Product("3DB35x410h30", "Dłuto 35x410 Hex30", family="chisel_flat",
                unit_dims=Dims(42, 6, 4), unit_weight_kg=1.2,
                carton=CartonSpec(10, Dims(44, 32, 14), 12.5))
    cs = cartons_for_line(p, 25)
    assert [c.units for c in cs] == [10, 10, 5]
    assert cs[0].full and not cs[2].full
    assert cs[2].weight_kg < cs[0].weight_kg
    assert per_layer_capacity((44, 32)) == 4  # 2 x 2 on 120 x 80
    res = pack_pallets(cs)
    assert len(res.pallets) == 1
    pal = res.pallets[0]
    assert pal.units == 25 and pal.load_height_cm == 14.0
    assert 0 < pal.fill_ratio < 0.1
    assert pal.room_for((44, 32), 14, 12.5) > 20
    assert res.issues == []


def test_pallet_height_limit_splits_pallets():
    p = Product("1WG80x800p", "Świder 80x800", family="auger", unit_dims=Dims(82, 10, 10), unit_weight_kg=3.0,
                carton=CartonSpec(4, Dims(84, 22, 22), 12.5))
    cs = plan_cartons({p.sku: p}, [(p.sku, 4 * 60)])  # 60 cartons
    res = pack_pallets(cs)
    # 84 x 22 footprint -> 1 x 3 per layer on 120 x 80 (84 along 120, 22 x 3 = 66 along 80)
    assert per_layer_capacity((84, 22)) == 3
    assert len(res.pallets) >= 2
    for pal in res.pallets:
        assert pal.load_height_cm <= A.PALLET_MAX_LOAD_HEIGHT_CM + 1e-9
        assert pal.gross_weight_kg <= A.PALLET_MAX_GROSS_KG + 1e-9
    # long single-unit exception: carton 84 cm is > 63.5 but holds 4 units -> flagged
    assert any("63.5" in i for i in res.issues)


def test_predictor_history_and_rules():
    hist = [HistoryLine("1WG80x800p", "XPO1", date(2026, 5, 1), 20) for _ in range(5)]
    hist += [HistoryLine("4APlus", "WRO5", date(2026, 6, 1), 30) for _ in range(3)]
    hist += [HistoryLine("4APlus", "XPO1", date(2024, 7, 1), 30)]
    hist += [HistoryLine("OLD", "HAJ1", date(2023, 7, 1), 30)] * 5
    pr = FCPredictor(hist, as_of=date(2026, 9, 1))
    a = pr.predict(None, sku="1WG80x800p")
    assert a.fc == "XPO1" and a.source == "history" and a.confidence > 0.8
    b = pr.predict(None, sku="4APlus")
    assert b.fc == "WRO5" and b.probs["WRO5"] > 0.8
    old = pr.predict(Product("OLD", "Adapter SDS Plus"), sku="OLD")
    assert old.source == "rule_name" and old.fc == "WRO5"  # pre-regime evidence ignored
    dims = pr.predict(Product("X", "coś", unit_dims=Dims(80, 10, 10), unit_weight_kg=2.0))
    assert dims.fc == "XPO1" and dims.source == "rule_dims"
    fam = pr.predict(Product("Y", "Świder glebowy 150 x 800 mm SDS Max"))
    assert fam.fc == "XPO1" and fam.source == "rule_name" and not fam.uncertain
    # grey zone sub-rules (docs/analiza/fc_rules.md)
    assert pr.predict(Product("G1", "Przedłużka do świdra 400 mm")).fc == "WRO5"
    assert pr.predict(Product("G2", "Dłuto płaskie 75 x 400 mm HEX28")).fc == "WRO5"
    assert pr.predict(Product("G3", "Szypa 135 x 410 mm HEX30")).fc == "XPO1"
    assert pr.predict(Product("G4", "Świder glebowy 80 mm Ø, 450 mm długości")).fc == "WRO5"
    assert pr.predict(Product("G5", "Świder glebowy 60 mm Ø, 450 mm długości")).fc == "XPO1"
    g6 = pr.predict(Product("G6", "Dłuto szpic 410 mm HEX30"))
    assert g6.fc == "XPO1" and g6.uncertain
    assert pr.predict(Product("G7", "WERHE Wiertło do ziemi 80 mm z SDS Plus do runa")).fc == "XPO1"  # auger, default 800 mm
    short = pr.predict(Product("Z", "Dłuto płaskie 25 x 250 mm SDS Plus"))
    assert short.fc == "WRO5"
    long_ = pr.predict(Product("Z2", "Dłuto płaskie 75 x 600 mm SDS Max"))
    assert long_.fc == "XPO1"
    ov = pr.predict(Product("O", "x", fc_override="WRO5"))
    assert ov.source == "override" and ov.fc == "WRO5"
    unk = pr.predict(Product("U", "zupełnie nieznany artykuł"))
    assert unk.source == "unknown" and unk.fc == ""
