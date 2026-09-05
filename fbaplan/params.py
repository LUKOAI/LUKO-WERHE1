"""Planner parameters (``data/planner_params.json``) and paths."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .rules import amazon as A

ROOT = Path(os.environ.get("FBAPLAN_HOME", Path(__file__).resolve().parent.parent))
DATA = ROOT / "data"
PATHS = {
    "products": DATA / "products.csv",
    "aliases": DATA / "product_aliases.csv",
    "history": DATA / "history",
    "verdicts": DATA / "verdicts.csv",
    "stock": DATA / "stock.csv",
    "params": DATA / "planner_params.json",
    "plans": DATA / "plans",
    "raw": DATA / "raw_history",
}

DEFAULTS = {
    "amazon": {},
    "predictor": {},
    "filler": {},
    "freight": {"pallet_rate_pln": None, "parcel_rate_pln": None},
    "capacity": {"standard_left_m3": None, "oversize_left_m3": None},
    "ui": {"port": 8765},
}


def load_params(path: Path | None = None) -> dict:
    path = path or PATHS["params"]
    p = json.loads(json.dumps(DEFAULTS))
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            user = json.load(fh)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(p.get(k), dict):
                p[k].update(v)
            else:
                p[k] = v
    A.apply_overrides(p)
    return p


def save_params(params: dict, path: Path | None = None) -> None:
    path = path or PATHS["params"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(params, fh, ensure_ascii=False, indent=1)
