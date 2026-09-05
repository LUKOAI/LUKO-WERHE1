"""FastAPI application. Run with ``python -m fbaplan serve --open``."""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from urllib.parse import quote as _q

from ..catalog.store import save_products
from ..stock import load_stock
from ..context import Context
from ..export import packing_rows, send_to_amazon_rows, summary_rows, to_csv, write_xlsx
from ..models import CartonSpec, Dims, PlanLine, Product
from ..params import save_params
from ..planner.filler import suggest
from ..planner.session import apply_verdict, evaluate, verdict_diff
from ..rules import amazon as A

TEMPLATES = Path(__file__).parent / "templates"


def _f(v: Optional[str]) -> Optional[float]:
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def _i(v: Optional[str]) -> Optional[int]:
    f = _f(v)
    return int(round(f)) if f is not None else None


def create_app(ctx: Context) -> FastAPI:
    app = FastAPI(title="FBA Plan — WERHE")
    tpl = Jinja2Templates(directory=str(TEMPLATES))
    tpl.env.filters["pct"] = lambda v: f"{(v or 0) * 100:.0f}%"
    tpl.env.filters["num"] = lambda v, d=0: ("" if v is None else f"{v:,.{d}f}".replace(",", " "))

    def render(request: Request, name: str, **kw) -> HTMLResponse:
        base = {"request": request, "ctx": ctx, "A": A, "today": date.today().isoformat(),
                "known_fcs": ctx.predictor.params["known_fcs"]}
        base.update(kw)
        return tpl.TemplateResponse(request, name, base)

    def eval_plan(plan):
        return evaluate(plan, ctx.products, ctx.predictor, ctx.stock, ctx.capacity_left(plan.target_fc))

    # ------------------------------------------------------------------ #
    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        plans = ctx.list_plans()
        no_dims = [p for p in ctx.products.values() if p.active and p.unit_dims is None and not (p.carton and p.carton.dims)]
        no_carton = [p for p in ctx.products.values() if p.active and (p.carton is None)]
        return render(request, "index.html", plans=plans, no_dims=no_dims, no_carton=no_carton,
                      n_products=len(ctx.products), n_history=len(ctx.history), n_stock=len(ctx.stock))

    # -- plans ----------------------------------------------------------- #
    @app.post("/plan/nowy")
    def plan_new(mode: str = Form("pallet"), target_fc: str = Form(""), max_pallets: int = Form(1)):
        plan = ctx.new_plan(mode=mode, target_fc=target_fc.strip(), max_pallets=max(1, max_pallets))
        return RedirectResponse(f"/plan/{plan.plan_id}", status_code=303)

    @app.get("/plan/{plan_id}", response_class=HTMLResponse)
    def plan_view(request: Request, plan_id: str, sugeruj: int = 1):
        plan = ctx.get_plan(plan_id)
        if not plan:
            return RedirectResponse("/", status_code=303)
        ev = eval_plan(plan)
        sug = suggest(ev, ctx.products, ctx.predictor, ctx.stock, ctx.stats, ctx.params.get("filler")) if sugeruj and plan.lines else []
        fr = ctx.params.get("freight", {})
        cost = ev.cost_per_unit(_f(fr.get("pallet_rate_pln")), _f(fr.get("parcel_rate_pln")))
        diff = verdict_diff(ev, plan.verdicts) if plan.verdicts else []
        return render(request, "plan.html", plan=plan, ev=ev, sug=sug, cost=cost, diff=diff,
                      products=sorted(ctx.products.values(), key=lambda p: p.name))

    @app.post("/plan/{plan_id}/dodaj")
    def plan_add(plan_id: str, sku: str = Form(...), qty: int = Form(...), brand: str = Form("")):
        plan = ctx.get_plan(plan_id)
        if plan:
            sku = sku.strip()
            if sku not in ctx.products:
                # allow "SKU — name" from the datalist
                sku = sku.split(" — ")[0].strip()
            for l in plan.lines:
                if l.sku == sku and l.brand == brand:
                    l.qty += max(0, qty)
                    break
            else:
                plan.lines.append(PlanLine(sku, max(0, qty), brand=brand))
            plan.lines = [l for l in plan.lines if l.qty > 0]
            ctx.save_plan(plan)
        return RedirectResponse(f"/plan/{plan_id}", status_code=303)

    @app.post("/plan/{plan_id}/ilosc")
    def plan_qty(plan_id: str, sku: str = Form(...), qty: int = Form(...)):
        plan = ctx.get_plan(plan_id)
        if plan:
            for l in plan.lines:
                if l.sku == sku:
                    l.qty = qty
            plan.lines = [l for l in plan.lines if l.qty > 0]
            ctx.save_plan(plan)
        return RedirectResponse(f"/plan/{plan_id}", status_code=303)

    @app.post("/plan/{plan_id}/usun")
    def plan_remove(plan_id: str, sku: str = Form(...), wyklucz: int = Form(0)):
        plan = ctx.get_plan(plan_id)
        if plan:
            plan.lines = [l for l in plan.lines if l.sku != sku]
            if wyklucz and sku not in plan.excluded_skus:
                plan.excluded_skus.append(sku)
            ctx.save_plan(plan)
        return RedirectResponse(f"/plan/{plan_id}", status_code=303)

    @app.post("/plan/{plan_id}/wyklucz")
    def plan_exclude(plan_id: str, sku: str = Form(...)):
        plan = ctx.get_plan(plan_id)
        if plan and sku not in plan.excluded_skus:
            plan.excluded_skus.append(sku)
            ctx.save_plan(plan)
        return RedirectResponse(f"/plan/{plan_id}", status_code=303)

    @app.post("/plan/{plan_id}/ustaw")
    def plan_settings(plan_id: str, mode: str = Form("pallet"), target_fc: str = Form(""), max_pallets: int = Form(1),
                      notes: str = Form(""), status: str = Form("draft")):
        plan = ctx.get_plan(plan_id)
        if plan:
            plan.mode, plan.target_fc, plan.max_pallets, plan.notes, plan.status = mode, target_fc.strip(), max(1, max_pallets), notes, status
            ctx.save_plan(plan)
        return RedirectResponse(f"/plan/{plan_id}", status_code=303)

    @app.post("/plan/{plan_id}/werdykt")
    async def plan_verdict(request: Request, plan_id: str):
        plan = ctx.get_plan(plan_id)
        if plan:
            form = await request.form()
            verdict = {k[3:]: str(v).strip().upper() for k, v in form.items() if k.startswith("fc_") and str(v).strip()}
            when = str(form.get("date") or date.today().isoformat())
            rows = apply_verdict(plan, verdict, when)
            ctx.save_plan(plan)
            ctx.record_verdict_rows(rows)
        return RedirectResponse(f"/plan/{plan_id}", status_code=303)

    @app.post("/plan/{plan_id}/dopelnij")
    def plan_autofill(plan_id: str, target_fill: float = Form(0.9), target_units: int = Form(150)):
        from ..planner.autofill import autofill

        plan = ctx.get_plan(plan_id)
        if plan:
            res = autofill(plan, ctx.products, ctx.predictor, ctx.stock, ctx.stats, ctx.params.get("filler"),
                           target_fill=target_fill, target_units=target_units, capacity_left_m3=ctx.capacity_left(plan.target_fc))
            plan.notes = (plan.notes + " | " if plan.notes else "") + "autofill: " + (", ".join(f"{s} +{q}" for s, q in res.added) or "nic") + f" ({res.stopped_because})"
            ctx.save_plan(plan)
        return RedirectResponse(f"/plan/{plan_id}", status_code=303)

    @app.post("/plan/{plan_id}/usun-plan")
    def plan_delete(plan_id: str):
        ctx.delete_plan(plan_id)
        return RedirectResponse("/", status_code=303)

    @app.post("/plan/{plan_id}/kopiuj")
    def plan_copy(plan_id: str):
        src = ctx.get_plan(plan_id)
        if not src:
            return RedirectResponse("/", status_code=303)
        plan = ctx.new_plan(mode=src.mode, target_fc=src.target_fc, max_pallets=src.max_pallets)
        plan.lines = [PlanLine(l.sku, l.qty, l.brand, l.msku, l.note) for l in src.lines]
        plan.excluded_skus = list(src.excluded_skus)
        ctx.save_plan(plan)
        return RedirectResponse(f"/plan/{plan.plan_id}", status_code=303)

    @app.get("/plan/{plan_id}/send_to_amazon.csv")
    def plan_csv(plan_id: str, fc: str = ""):
        plan = ctx.get_plan(plan_id)
        if not plan:
            return RedirectResponse("/", status_code=303)
        ev = eval_plan(plan)
        body = to_csv(send_to_amazon_rows(ev, fc or None), ",")
        return Response(body, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{plan_id}_send_to_amazon.csv"'})

    @app.get("/plan/{plan_id}/plan.xlsx")
    def plan_xlsx(plan_id: str):
        plan = ctx.get_plan(plan_id)
        if not plan:
            return RedirectResponse("/", status_code=303)
        ev = eval_plan(plan)
        buf = io.BytesIO()
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            write_xlsx(tmp.name, {"Pozycje": send_to_amazon_rows(ev), "Pakowanie": packing_rows(ev), "Palety": summary_rows(ev)})
            buf.write(Path(tmp.name).read_bytes())
        Path(tmp.name).unlink(missing_ok=True)
        return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{plan_id}.xlsx"'})

    # -- catalog --------------------------------------------------------- #
    @app.get("/katalog", response_class=HTMLResponse)
    def catalog(request: Request, q: str = "", brak: str = ""):
        items = list(ctx.products.values())
        if q:
            ql = q.lower()
            items = [p for p in items if ql in p.sku.lower() or ql in p.name.lower()]
        if brak == "wymiary":
            items = [p for p in items if p.unit_dims is None]
        preds = {p.sku: ctx.predictor.predict(p) for p in items}
        stats = ctx.stats.by_sku
        return render(request, "katalog.html", items=sorted(items, key=lambda p: p.name), q=q, preds=preds, stats=stats)

    @app.get("/katalog/{sku}", response_class=HTMLResponse)
    def product_view(request: Request, sku: str):
        p = ctx.products.get(sku)
        if not p:
            return RedirectResponse("/katalog", status_code=303)
        pred = ctx.predictor.predict(p)
        tier = A.size_tier(p.unit_dims, p.unit_weight_kg)
        ev = ctx.predictor.evidence_for(sku)
        aliases = [a for a in ctx.aliases if a.sku == sku]
        return render(request, "produkt.html", p=p, pred=pred, tier=tier, evidence=sorted(ev, key=lambda h: h.when, reverse=True)[:40],
                      aliases=aliases, st=ctx.stats.by_sku.get(sku), stock=ctx.stock.get(sku))

    @app.post("/katalog/{sku}")
    async def product_save(request: Request, sku: str):
        form = await request.form()
        p = ctx.products.get(sku)
        new = p is None
        if new:
            p = Product(sku=sku, name=str(form.get("name") or sku))
        g = lambda k: str(form.get(k) or "").strip()
        p.name = g("name") or p.name
        p.family = g("family")
        p.brands = [b for b in g("brands").replace(",", ";").split(";") if b.strip()]
        p.mskus = {k: v for k, v in (("WERHE", g("msku_werhe")), ("WERKON", g("msku_werkon"))) if v}
        p.unit_dims = Dims.parse(g("unit_length_cm"), g("unit_width_cm"), g("unit_height_cm"))
        p.unit_weight_kg = _f(g("unit_weight_kg"))
        upc = _i(g("units_per_carton"))
        p.carton = CartonSpec(upc, Dims.parse(g("carton_length_cm"), g("carton_width_cm"), g("carton_height_cm")), _f(g("carton_weight_kg"))) if upc else None
        p.fc_override = g("fc_override").upper() or None
        p.pack_group = g("pack_group")
        p.max_qty_per_plan = _i(g("max_qty_per_plan"))
        p.active = g("active") == "1"
        p.notes = g("notes")
        ctx.products[sku] = p
        save_products(ctx.paths["products"], ctx.products.values())
        return RedirectResponse(f"/katalog/{sku}", status_code=303)

    @app.post("/katalog-nowy")
    def product_new(sku: str = Form(...), name: str = Form("")):
        sku = sku.strip()
        if sku and sku not in ctx.products:
            ctx.products[sku] = Product(sku=sku, name=name.strip() or sku)
            save_products(ctx.paths["products"], ctx.products.values())
        return RedirectResponse(f"/katalog/{sku}", status_code=303)

    # -- history --------------------------------------------------------- #
    @app.get("/historia", response_class=HTMLResponse)
    def history(request: Request, top: int = 80):
        rows = sorted(ctx.stats.by_sku.values(), key=lambda s: -s.units_12m)[:top]
        return render(request, "historia.html", rows=rows, st=ctx.stats)

    # -- settings -------------------------------------------------------- #
    @app.get("/ustawienia", response_class=HTMLResponse)
    def settings(request: Request):
        return render(request, "ustawienia.html", params=ctx.params, filler=ctx.params.get("filler", {}), predictor=ctx.predictor.params)

    @app.post("/ustawienia")
    async def settings_save(request: Request):
        form = await request.form()
        g = lambda k: str(form.get(k) or "").strip()
        ctx.params.setdefault("freight", {})["pallet_rate_pln"] = _f(g("pallet_rate_pln"))
        ctx.params["freight"]["parcel_rate_pln"] = _f(g("parcel_rate_pln"))
        ctx.params.setdefault("capacity", {})["standard_left_m3"] = _f(g("standard_left_m3"))
        ctx.params["capacity"]["oversize_left_m3"] = _f(g("oversize_left_m3"))
        fl = ctx.params.setdefault("filler", {})
        for k in ("w_fc", "w_sales", "w_stock", "w_fit", "w_affinity", "min_fc_prob", "target_cover_days", "max_suggestions", "default_qty_cartons"):
            v = _f(g(k))
            if v is not None:
                fl[k] = v
        pr = ctx.params.setdefault("predictor", {})
        for k in ("half_life_months", "min_weight"):
            v = _f(g(k))
            if v is not None:
                pr[k] = v
                ctx.predictor.params[k] = v
        save_params(ctx.params, ctx.paths["params"])
        return RedirectResponse("/ustawienia", status_code=303)

    # -- imports --------------------------------------------------------- #
    @app.get("/import", response_class=HTMLResponse)
    def import_page(request: Request, msg: str = ""):
        return render(request, "import.html", msg=msg)

    @app.post("/import/fee-preview")
    async def import_fee(file: UploadFile = File(...), overwrite: int = Form(0)):
        from ..imports import import_fee_preview

        data = await file.read()
        rep = import_fee_preview(file.filename or "fee.txt", ctx.products, ctx.resolver(), ctx.paths["products"], data=data, overwrite=bool(overwrite))
        msg = "Podgląd opłat: " + rep.summary() + ("; nierozpoznane: " + "; ".join(rep.unmatched[:15]) if rep.unmatched else "")
        return RedirectResponse("/import?msg=" + _q(msg), status_code=303)

    @app.post("/import/stock")
    async def import_stock(file: UploadFile = File(...), replace: int = Form(0)):
        from ..imports import import_inventory_report

        data = await file.read()
        rep = import_inventory_report(file.filename or "stock.txt", ctx.products, ctx.resolver(), ctx.paths["stock"], ctx.paths["products"], data=data, merge=not replace)
        ctx.stock = load_stock(ctx.paths["stock"], ctx.products)
        msg = "Zapasy: " + rep.summary() + ("; nierozpoznane: " + "; ".join(rep.unmatched[:15]) if rep.unmatched else "")
        return RedirectResponse("/import?msg=" + _q(msg), status_code=303)

    @app.post("/import/catalog")
    async def import_catalog(file: UploadFile = File(...)):
        from ..imports import import_catalog_xlsx

        data = await file.read()
        rep = import_catalog_xlsx(file.filename or "katalog.xlsx", ctx.products, ctx.paths["products"], data=data)
        return RedirectResponse("/import?msg=" + _q("Katalog: " + rep.summary()), status_code=303)

    @app.get("/import/katalog.xlsx")
    def export_catalog():
        import tempfile

        from ..imports import export_catalog_xlsx

        prio = {s: st.units_12m for s, st in ctx.stats.by_sku.items()}
        fc = {s: ctx.predictor.predict(p).fc for s, p in ctx.products.items()}
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            export_catalog_xlsx(tmp.name, ctx.products.values(), prio, fc)
            body = Path(tmp.name).read_bytes()
        Path(tmp.name).unlink(missing_ok=True)
        return Response(body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="katalog_do_uzupelnienia.xlsx"'})

    @app.post("/przeladuj")
    def reload():
        new = Context.load(ctx.paths, ctx.as_of)
        ctx.__dict__.update(new.__dict__)
        return RedirectResponse("/", status_code=303)

    return app
