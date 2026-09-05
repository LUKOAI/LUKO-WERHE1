import csv
from datetime import date
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from fbaplan.context import Context  # noqa: E402
from fbaplan.web.app import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path: Path):
    data = tmp_path / "data"
    (data / "history").mkdir(parents=True)
    with open(data / "products.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["sku", "name", "family", "brands", "msku_werhe", "msku_werkon", "unit_length_cm", "unit_width_cm", "unit_height_cm",
                    "unit_weight_kg", "units_per_carton", "carton_length_cm", "carton_width_cm", "carton_height_cm", "carton_weight_kg",
                    "fc_override", "pack_group", "max_qty_per_plan", "active", "notes"])
        w.writerow(["1WG80x800p", "Świder 80x800 SDS Plus", "auger", "WERHE;WERKON", "WH-80x800", "WK-80x800", 82, 10, 10, 3.0, 4, 84, 22, 22, 12.5, "", "dlugie", "", 1, ""])
        w.writerow(["1WG100x800p", "Świder 100x800 SDS Plus", "auger", "WERHE", "WH-100x800", "", 82, 12, 12, 3.6, 4, 84, 26, 26, 15, "", "dlugie", "", 1, ""])
        w.writerow(["4APlus", "Adapter SDS Plus", "adapter", "WERHE", "WH-4APLUS", "", 12, 5, 5, 0.2, 50, 40, 30, 20, 10.5, "", "male", "", 1, ""])
    with open(data / "history" / "lines.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["uid", "month", "date", "shipment_id", "fc", "kind", "pos", "name", "qty", "skus", "sku", "brand", "resolve_conf", "resolve_how"])
        for i in range(5):
            w.writerow([f"S{i}", "2026-05", "2026-05-01", f"FBA{i}", "XPO1", "pallet", 1, "x", 20, "", "1WG80x800p", "WERHE", 1, "sku"])
            w.writerow([f"S{i}", "2026-05", "2026-05-01", f"FBA{i}", "XPO1", "pallet", 2, "x", 8, "", "1WG100x800p", "WERHE", 1, "sku"])
            w.writerow([f"T{i}", "2026-06", "2026-06-01", f"FBB{i}", "WRO5", "parcel", 1, "x", 100, "", "4APlus", "WERHE", 1, "sku"])
    with open(data / "stock.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["sku", "fba_available", "fba_inbound", "sales_30d", "sales_90d"])
        w.writerow(["1WG100x800p", 3, 0, 40, 100])
    paths = {"products": data / "products.csv", "aliases": data / "product_aliases.csv", "history": data / "history",
             "verdicts": data / "verdicts.csv", "stock": data / "stock.csv", "params": data / "planner_params.json",
             "plans": data / "plans", "raw": data / "raw"}
    ctx = Context.load(paths, as_of=date(2026, 9, 1))
    return TestClient(create_app(ctx)), ctx, data


def test_full_flow(client):
    c, ctx, data = client
    assert c.get("/").status_code == 200
    r = c.post("/plan/nowy", data={"mode": "pallet", "target_fc": "", "max_pallets": 1}, follow_redirects=False)
    assert r.status_code == 303
    pid = r.headers["location"].split("/")[-1]
    r = c.post(f"/plan/{pid}/dodaj", data={"sku": "1WG80x800p", "qty": 40, "brand": "WERHE"}, follow_redirects=True)
    assert r.status_code == 200
    html = r.text
    assert "XPO1" in html and "Propozycje dopełnienia" in html
    assert "1WG100x800p" in html  # suggested filler (same FC, low stock)
    assert "4APlus" not in html.split("Propozycje dopełnienia")[1].split("Decyzja Amazona")[0]
    # add a WRO5 product -> split warning
    c.post(f"/plan/{pid}/dodaj", data={"sku": "4APlus", "qty": 50, "brand": ""})
    html = c.get(f"/plan/{pid}").text
    assert "podzielony" in html
    # exports
    csv_ = c.get(f"/plan/{pid}/send_to_amazon.csv").text
    assert "WH-80x800" in csv_ and "WH-4APLUS" in csv_
    only = c.get(f"/plan/{pid}/send_to_amazon.csv?fc=XPO1").text
    assert "WH-80x800" in only and "WH-4APLUS" not in only
    x = c.get(f"/plan/{pid}/plan.xlsx")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    # verdict: Amazon sent the adapter to XPO1 -> predictor learns
    r = c.post(f"/plan/{pid}/werdykt", data={"date": "2026-09-02", "fc_1WG80x800p": "XPO1", "fc_4APlus": "XPO1"}, follow_redirects=True)
    assert (data / "verdicts.csv").exists()
    assert "zdecydował inaczej" in r.text
    pred = ctx.predictor.predict(ctx.products["4APlus"])
    assert pred.probs["XPO1"] > 0.2
    # catalog edit
    r = c.post("/katalog/4APlus", data={"name": "Adapter SDS Plus", "family": "adapter", "brands": "WERHE", "msku_werhe": "WH-4APLUS",
                                        "msku_werkon": "", "unit_length_cm": "12", "unit_width_cm": "5", "unit_height_cm": "5",
                                        "unit_weight_kg": "0.2", "units_per_carton": "50", "carton_length_cm": "40", "carton_width_cm": "30",
                                        "carton_height_cm": "20", "carton_weight_kg": "10.5", "fc_override": "wro5", "pack_group": "male",
                                        "max_qty_per_plan": "", "active": "1", "notes": ""}, follow_redirects=True)
    assert r.status_code == 200 and ctx.products["4APlus"].fc_override == "WRO5"
    rows = list(csv.DictReader(open(data / "products.csv", encoding="utf-8")))
    assert next(r for r in rows if r["sku"] == "4APlus")["fc_override"] == "WRO5"
    # settings + other pages
    assert c.post("/ustawienia", data={"pallet_rate_pln": "450", "parcel_rate_pln": "25", "standard_left_m3": "", "oversize_left_m3": "3",
                                        "w_fc": "3", "half_life_months": "12", "min_weight": "1.5"}, follow_redirects=True).status_code == 200
    assert ctx.params["freight"]["pallet_rate_pln"] == 450.0
    assert "zł/szt." in c.get(f"/plan/{pid}").text
    for url in ("/katalog", "/katalog?q=świder", "/katalog/1WG80x800p", "/historia", "/ustawienia"):
        assert c.get(url).status_code == 200, url
    assert c.post(f"/plan/{pid}/kopiuj", follow_redirects=False).status_code == 303
    assert len(ctx.list_plans()) == 2
