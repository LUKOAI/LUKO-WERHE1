"""Application context: loads catalog, history, stock and parameters once and
exposes the predictor, statistics and plan storage to the CLI and the web UI."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .catalog.store import Resolver, load_aliases, load_products
from .history.store import HistoryStats, append_verdicts, compute_stats, load_history_lines
from .models import Alias, HistoryLine, Plan, Product, StockRow, new_plan_id
from .params import PATHS, load_params
from .predict.fc import FCPredictor
from .stock import load_stock


@dataclass
class Context:
    params: dict
    products: dict[str, Product]
    aliases: list[Alias]
    history: list[HistoryLine]
    stock: dict[str, StockRow]
    predictor: FCPredictor
    stats: HistoryStats
    paths: dict[str, Path] = field(default_factory=lambda: dict(PATHS))
    as_of: date = field(default_factory=date.today)

    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, paths: Optional[dict[str, Path]] = None, as_of: Optional[date] = None) -> "Context":
        paths = dict(paths or PATHS)
        params = load_params(paths["params"])
        products = load_products(paths["products"])
        aliases = load_aliases(paths["aliases"])
        history = load_history_lines(paths["history"]) if paths["history"].exists() else []
        history += _verdicts_if_separate(paths)
        as_of = as_of or date.today()
        predictor = FCPredictor(history, params.get("predictor"), as_of=as_of)
        stats = compute_stats(history, as_of=as_of, regime_start=predictor.params["regime_start"])
        stock = load_stock(paths["stock"], products)
        from .catalog.cartons import infer_carton

        for p in products.values():
            spec = infer_carton(p, stats.by_sku.get(p.sku))
            if spec:
                p.carton = spec
        return cls(params, products, aliases, history, stock, predictor, stats, paths, as_of)

    def resolver(self) -> Resolver:
        return Resolver(self.products, self.aliases)

    # -- plans ----------------------------------------------------------- #
    def plans_dir(self) -> Path:
        d = self.paths["plans"]
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_plans(self) -> list[Plan]:
        out = []
        for f in sorted(self.plans_dir().glob("*.json"), reverse=True):
            try:
                out.append(Plan.from_json(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return out

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        f = self.plans_dir() / f"{plan_id}.json"
        return Plan.from_json(f.read_text(encoding="utf-8")) if f.exists() else None

    def save_plan(self, plan: Plan) -> None:
        (self.plans_dir() / f"{plan.plan_id}.json").write_text(plan.to_json(), encoding="utf-8")

    def new_plan(self, mode: str = "pallet", target_fc: str = "", max_pallets: int = 1) -> Plan:
        base = new_plan_id()
        pid, n = base, 1
        while (self.plans_dir() / f"{pid}.json").exists():
            n += 1
            pid = f"{base}-{n}"
        p = Plan(pid, datetime.now().isoformat(timespec="seconds"), mode=mode, target_fc=target_fc, max_pallets=max_pallets)
        self.save_plan(p)
        return p

    def delete_plan(self, plan_id: str) -> bool:
        f = self.plans_dir() / f"{plan_id}.json"
        if f.exists():
            f.unlink()
            return True
        return False

    def record_verdict_rows(self, rows: list[dict]) -> None:
        append_verdicts(self.paths["verdicts"], rows)
        for r in rows:
            h = HistoryLine(r["sku"], r["fc"], date.fromisoformat(r["date"][:10]), int(r.get("qty") or 0), "", "", "verdict")
            self.history.append(h)
            self.predictor.add(h)

    # -- capacity -------------------------------------------------------- #
    def capacity_left(self, fc: str) -> Optional[float]:
        cap = self.params.get("capacity", {})
        pred = self.predictor.params
        key = "standard_left_m3" if fc == pred["sortable_fc"] else "oversize_left_m3"
        v = cap.get(key)
        return float(v) if v not in (None, "") else None


def _verdicts_if_separate(paths: dict[str, Path]) -> list[HistoryLine]:
    """load_history_lines() already reads data/verdicts.csv next to history/; only load
    separately when the verdicts path is elsewhere."""
    from .history.store import load_verdicts

    default = paths["history"].parent / "verdicts.csv"
    if paths["verdicts"].resolve() != default.resolve() or not paths["history"].exists():
        return load_verdicts(paths["verdicts"])
    return []
