"""Import historical shipment files into the unified history and query it."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from ..catalog.store import Resolver
from ..models import HistoryLine
from .parsers import PARSERS, parse_file

SHIP_COLUMNS = ["uid", "source_file", "created_at", "month", "shipment_id", "reference_id", "fc", "kind", "n_lines", "units", "notes"]
LINE_COLUMNS = ["uid", "month", "date", "shipment_id", "fc", "kind", "pos", "name", "qty", "skus", "sku", "brand", "resolve_conf", "resolve_how"]
VERDICT_COLUMNS = ["date", "plan_id", "sku", "fc", "qty", "shipment_id", "note"]


def _kind(suffix: str) -> str:
    s = (suffix or "").lower()
    if "palet" in s:
        return "pallet"
    if "paczk" in s or "parcel" in s:
        return "parcel"
    return ""


def import_files(paths: Iterable[Path | str], resolver: Resolver, out_dir: Path | str) -> tuple[int, int, int]:
    """Parse files, resolve names to SKUs, write shipments.csv / lines.csv. Returns (shipments, lines, unresolved)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ship_rows, line_rows = [], []
    n = 0
    unresolved = 0
    for path in sorted(Path(p) for p in paths):
        if path.suffix.lower() not in PARSERS:
            continue
        for sh in parse_file(path):
            n += 1
            uid = f"S{n:05d}"
            created = sh.created_at.isoformat() if sh.created_at else ""
            month = sh.created_at.strftime("%Y-%m") if sh.created_at else path.name[:7]
            kind = _kind(sh.header_suffix)
            ship_rows.append(dict(uid=uid, source_file=path.name, created_at=created, month=month,
                                  shipment_id=sh.shipment_id or "", reference_id=sh.reference_id or "", fc=sh.fc or "",
                                  kind=kind, n_lines=len(sh.lines), units=sh.units, notes=" | ".join(sh.notes)))
            for i, l in enumerate(sh.lines, 1):
                sku, brand, conf, how = resolver.resolve(l.name, l.skus)
                if not sku:
                    unresolved += 1
                line_rows.append(dict(uid=uid, month=month, date=created[:10], shipment_id=sh.shipment_id or "", fc=sh.fc or "",
                                      kind=kind, pos=i, name=l.name, qty=l.qty if l.qty is not None else "",
                                      skus=";".join(l.skus), sku=sku or "", brand=brand, resolve_conf=conf, resolve_how=how))
    _write(out_dir / "shipments.csv", SHIP_COLUMNS, ship_rows)
    _write(out_dir / "lines.csv", LINE_COLUMNS, line_rows)
    return len(ship_rows), len(line_rows), unresolved


def _write(path: Path, cols: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def _date(s: str, month: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.strptime(month + "-01", "%Y-%m-%d").date()
    except ValueError:
        return None


def load_history_lines(hist_dir: Path | str) -> list[HistoryLine]:
    """History lines with a resolved SKU (from lines.csv) plus recorded verdicts."""
    hist_dir = Path(hist_dir)
    out: list[HistoryLine] = []
    lp = hist_dir / "lines.csv"
    if lp.exists():
        with open(lp, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                d = _date(r.get("date") or "", r.get("month") or "")
                if not d or not r.get("sku"):
                    continue
                try:
                    qty = int(float(r.get("qty") or 0))
                except ValueError:
                    qty = 0
                out.append(HistoryLine(r["sku"], r.get("fc") or "", d, qty, r.get("shipment_id") or "", r.get("kind") or "", "history", r.get("name") or ""))
    out += load_verdicts(hist_dir.parent / "verdicts.csv")
    return out


def load_verdicts(path: Path | str) -> list[HistoryLine]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            d = _date(r.get("date") or "", "")
            if not d or not r.get("sku") or not r.get("fc"):
                continue
            try:
                qty = int(float(r.get("qty") or 0))
            except ValueError:
                qty = 0
            out.append(HistoryLine(r["sku"], r["fc"], d, qty, r.get("shipment_id") or "", "", "verdict"))
    return out


def append_verdicts(path: Path | str, rows: Iterable[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=VERDICT_COLUMNS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in VERDICT_COLUMNS})


# --------------------------------------------------------------------------- #
# Statistics used by the planner
# --------------------------------------------------------------------------- #
@dataclass
class SkuStats:
    sku: str
    units_12m: int = 0
    lines_12m: int = 0
    units_24m: int = 0
    months_active_12m: int = 0
    last_shipped: Optional[date] = None
    typical_qty: int = 0          # most common line quantity (recent)
    qty_counter: Counter = field(default_factory=Counter)
    fc_counter: Counter = field(default_factory=Counter)

    @property
    def monthly_units(self) -> float:
        return self.units_12m / 12.0


@dataclass
class HistoryStats:
    by_sku: dict[str, SkuStats]
    pair_counts: Counter            # (sku_a, sku_b) -> number of shipments containing both (regime only)
    sku_ship_counts: Counter        # sku -> number of shipments (regime only)
    n_shipments: int

    def affinity(self, a: str, b: str) -> float:
        """Lift of co-shipment vs independence (1 = independent, >1 = shipped together more than expected)."""
        if not self.n_shipments:
            return 0.0
        pa, pb = self.sku_ship_counts[a] / self.n_shipments, self.sku_ship_counts[b] / self.n_shipments
        pab = self.pair_counts[tuple(sorted((a, b)))] / self.n_shipments
        return pab / (pa * pb) if pa and pb else 0.0


def compute_stats(lines: Iterable[HistoryLine], as_of: Optional[date] = None, regime_start: str = "2024-06-01") -> HistoryStats:
    as_of = as_of or date.today()
    start = date.fromisoformat(regime_start)
    by: dict[str, SkuStats] = {}
    ship_skus: dict[str, set[str]] = defaultdict(set)
    for h in lines:
        if h.source != "history":
            continue
        s = by.setdefault(h.sku, SkuStats(h.sku))
        months = (as_of.year - h.when.year) * 12 + (as_of.month - h.when.month)
        if months < 24:
            s.units_24m += h.qty
        if months < 12:
            s.units_12m += h.qty
            s.lines_12m += 1
            s.qty_counter[h.qty] += 1
        if s.last_shipped is None or h.when > s.last_shipped:
            s.last_shipped = h.when
        if h.fc:
            s.fc_counter[h.fc] += 1
        if h.when >= start:
            ship_skus[h.shipment_id or f"{h.when}-{h.fc}-{id(h)}"].add(h.sku)
    months_active: dict[str, set[str]] = defaultdict(set)
    for h in lines:
        if h.source == "history":
            months = (as_of.year - h.when.year) * 12 + (as_of.month - h.when.month)
            if months < 12:
                months_active[h.sku].add(h.when.strftime("%Y-%m"))
    for sku, s in by.items():
        s.months_active_12m = len(months_active.get(sku, ()))
        if s.qty_counter:
            s.typical_qty = s.qty_counter.most_common(1)[0][0]
    pair = Counter()
    single = Counter()
    for skus in ship_skus.values():
        for a in skus:
            single[a] += 1
        for a, b in __import__("itertools").combinations(sorted(skus), 2):
            pair[(a, b)] += 1
    return HistoryStats(by, pair, single, len(ship_skus))
