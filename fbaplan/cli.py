"""Command line interface: ``python -m fbaplan <command>``."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .context import Context
from .params import PATHS


def cmd_import_history(a: argparse.Namespace) -> int:
    from .history.store import import_files

    ctx = Context.load()
    src = Path(a.src) if a.src else PATHS["raw"]
    files = [p for p in src.rglob("*") if p.suffix.lower() in (".docx", ".xlsx", ".pdf")]
    if not files:
        print(f"Brak plików docx/xlsx/pdf w {src}")
        return 1
    n, m, unresolved = import_files(files, ctx.resolver(), PATHS["history"])
    print(f"Zaimportowano {n} wysyłek, {m} pozycji z {len(files)} plików; nierozpoznanych nazw: {unresolved}")
    print(f"Wynik: {PATHS['history']}/shipments.csv, lines.csv")
    return 0


def cmd_predict(a: argparse.Namespace) -> int:
    ctx = Context.load()
    skus = a.sku or sorted(ctx.products)
    print(f"{'SKU':18} {'FC':6} {'p':>5} {'pewn.':>5}  źródło        wyjaśnienie")
    for s in skus:
        pr = ctx.predictor.predict(ctx.products.get(s), sku=s)
        print(f"{s:18} {pr.fc or '?':6} {pr.prob(pr.fc):5.0%} {pr.confidence:5.0%}  {pr.source:13} {pr.explanation}")
    return 0


def cmd_stats(a: argparse.Namespace) -> int:
    ctx = Context.load()
    st = ctx.stats
    rows = sorted(st.by_sku.values(), key=lambda s: -s.units_12m)[: a.top]
    print(f"Historia: {len(ctx.history)} pozycji, {len(st.by_sku)} SKU, {st.n_shipments} wysyłek w bieżącym reżimie")
    print(f"{'SKU':18} {'12 mies.':>8} {'linii':>6} {'typowo':>7} {'mies.akt':>8} {'ostatnia':>10}  FC")
    for s in rows:
        fcs = ", ".join(f"{k}:{v}" for k, v in s.fc_counter.most_common(2))
        print(f"{s.sku:18} {s.units_12m:8d} {s.lines_12m:6d} {s.typical_qty:7d} {s.months_active_12m:8d} {str(s.last_shipped):>10}  {fcs}")
    return 0


def _parse_lines(items: list[str]) -> list[tuple[str, int]]:
    out = []
    for it in items:
        if "=" not in it:
            raise SystemExit(f"Pozycja musi mieć postać SKU=ILOŚĆ, nie: {it}")
        s, q = it.split("=", 1)
        out.append((s.strip(), int(q)))
    return out


def cmd_plan(a: argparse.Namespace) -> int:
    from .models import PlanLine
    from .planner.filler import suggest
    from .planner.session import evaluate

    ctx = Context.load()
    plan = ctx.new_plan(mode=a.mode, target_fc=a.fc or "", max_pallets=a.pallets)
    plan.lines = [PlanLine(s, q) for s, q in _parse_lines(a.items)]
    ev = evaluate(plan, ctx.products, ctx.predictor, ctx.stock, ctx.capacity_left(plan.target_fc or ""))
    ctx.save_plan(plan)
    print(f"Plan {plan.plan_id} ({plan.mode}), magazyn główny: {ev.anchor_fc or '?'}, {ev.units} szt., {ev.volume_m3:.2f} m³")
    for fc, g in ev.groups.items():
        print(f"  {fc}: {g.units} szt., {g.cartons} kartonów, {len(g.pallets)} palet, wypełnienie ostatniej palety {g.fill_ratio:.0%}, {g.weight_kg:.0f} kg")
        for le in g.lines:
            print(f"     {le.line.sku:18} {le.qty:5d} szt.  {le.prediction.fc or '?':5} {le.prediction.confidence:4.0%}  {le.prediction.explanation}")
    for w in ev.warnings:
        print("  ! " + w)
    if a.suggest:
        print("\nPropozycje dopełnienia:")
        for s in suggest(ev, ctx.products, ctx.predictor, ctx.stock, ctx.stats, ctx.params.get("filler"))[: a.suggest]:
            print(f"  {s.sku:18} {s.qty:5d} szt. ({s.cartons} kart.)  score {s.score:.2f}  " + "; ".join(s.reasons) + ("  !! " + "; ".join(s.problems) if s.problems else ""))
    if a.export:
        from .export import export_plan

        files = export_plan(ev, a.export)
        print("Eksport:", ", ".join(str(p) for p in files.values()))
    return 0


def cmd_verdict(a: argparse.Namespace) -> int:
    from .planner.session import apply_verdict

    ctx = Context.load()
    plan = ctx.get_plan(a.plan_id)
    if not plan:
        print("Nie ma takiego planu")
        return 1
    verdict = {s: fc for s, fc in (x.split("=", 1) for x in a.items)}
    rows = apply_verdict(plan, verdict, a.date or date.today().isoformat())
    ctx.save_plan(plan)
    ctx.record_verdict_rows(rows)
    print(f"Zapisano werdykt dla {len(rows)} pozycji planu {plan.plan_id} → {PATHS['verdicts']}")
    return 0


def cmd_serve(a: argparse.Namespace) -> int:
    import uvicorn

    from .web.app import create_app

    ctx = Context.load()
    port = a.port or int(ctx.params.get("ui", {}).get("port", 8765))
    if a.open:
        import threading
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    uvicorn.run(create_app(ctx), host="127.0.0.1", port=port, log_level="warning")
    return 0


def cmd_stock_template(a: argparse.Namespace) -> int:
    from .stock import save_stock_template

    ctx = Context.load()
    save_stock_template(a.out or PATHS["stock"], ctx.products)
    print("Zapisano szablon", a.out or PATHS["stock"])
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fbaplan", description="Planowanie wysyłek do Amazon FBA (WERHE)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("import-history", help="importuj historyczne plany (docx/xlsx/pdf) do data/history")
    s.add_argument("--src", help="katalog z plikami (domyślnie data/raw_history)")
    s.set_defaults(fn=cmd_import_history)

    s = sub.add_parser("predict", help="przewiduj magazyn dla SKU")
    s.add_argument("sku", nargs="*")
    s.set_defaults(fn=cmd_predict)

    s = sub.add_parser("stats", help="statystyki historii per SKU")
    s.add_argument("--top", type=int, default=40)
    s.set_defaults(fn=cmd_stats)

    s = sub.add_parser("plan", help="oceń plan: SKU=ILOŚĆ ...")
    s.add_argument("items", nargs="+")
    s.add_argument("--mode", choices=["pallet", "parcel"], default="pallet")
    s.add_argument("--fc", help="wymuś magazyn główny")
    s.add_argument("--pallets", type=int, default=1)
    s.add_argument("--suggest", type=int, default=10, help="ile propozycji dopełnienia pokazać (0 = brak)")
    s.add_argument("--export", help="katalog na eksport (csv + xlsx)")
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("verdict", help="zapisz decyzję Amazona: PLAN_ID SKU=FC ...")
    s.add_argument("plan_id")
    s.add_argument("items", nargs="+")
    s.add_argument("--date")
    s.set_defaults(fn=cmd_verdict)

    s = sub.add_parser("stock-template", help="zapisz szablon data/stock.csv")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_stock_template)

    s = sub.add_parser("serve", help="uruchom interfejs www (lokalnie)")
    s.add_argument("--port", type=int)
    s.add_argument("--open", action="store_true", help="otwórz przeglądarkę")
    s.set_defaults(fn=cmd_serve)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
