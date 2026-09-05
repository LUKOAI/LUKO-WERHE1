"""Catalog storage: products (``data/products.csv``) and name aliases
(``data/product_aliases.csv``), plus name -> SKU resolution."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from ..models import Alias, Product
from .normalize import extract

ALIAS_COLUMNS = ["name", "sku", "brand", "confidence", "source"]


def _norm(s: str) -> str:
    s = (s or "").lower().replace("®", " ").replace("™", " ")
    s = re.sub(r"[\s ]+", " ", s)
    return s.strip(" -–—|,.;:")


def load_products(path: Path | str) -> dict[str, Product]:
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    out: dict[str, Product] = {}
    for r in rows:
        if not (r.get("sku") or "").strip():
            continue
        p = Product.from_row(r)
        out[p.sku] = p
    return out


def save_products(path: Path | str, products: Iterable[Product]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=Product.CSV_COLUMNS)
        w.writeheader()
        for p in sorted(products, key=lambda p: p.sku):
            w.writerow(p.to_row())


def load_aliases(path: Path | str) -> list[Alias]:
    path = Path(path)
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        if not (r.get("name") and r.get("sku")):
            continue
        try:
            conf = float(r.get("confidence") or 1.0)
        except ValueError:
            conf = 1.0
        out.append(Alias(r["name"], r["sku"].strip(), (r.get("brand") or "").strip(), conf, r.get("source") or ""))
    return out


def save_aliases(path: Path | str, aliases: Iterable[Alias]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(ALIAS_COLUMNS)
        for a in sorted(aliases, key=lambda a: (a.sku, a.name)):
            w.writerow([a.name, a.sku, a.brand, f"{a.confidence:.2f}", a.source])


def brand_from_name(name: str) -> str:
    n = (name or "").lower()
    if "werkon" in n:
        return "WERKON"
    if "werhe" in n:
        return "WERHE"
    return ""


@dataclass
class Resolver:
    """Resolve a free-text product name (listing title, Apilo name) to a canonical SKU."""

    products: dict[str, Product]
    aliases: list[Alias] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._exact: dict[str, Alias] = {}
        self._fkey: dict[str, dict[str, float]] = {}
        for a in self.aliases:
            self._exact.setdefault(_norm(a.name), a)
            fk = extract(a.name).key()
            if fk and fk != "other":
                self._fkey.setdefault(fk, {})
                self._fkey[fk][a.sku] = self._fkey[fk].get(a.sku, 0.0) + a.confidence
        for p in self.products.values():
            self._exact.setdefault(_norm(p.name), Alias(p.name, p.sku, "", 1.0, "catalog"))
            self._exact.setdefault(_norm(p.sku), Alias(p.sku, p.sku, "", 1.0, "catalog"))

    def resolve(self, name: str, skus: Optional[list[str]] = None) -> tuple[Optional[str], str, float, str]:
        """Return (sku, brand, confidence, how)."""
        brand = brand_from_name(name)
        if skus:
            for s in skus:
                if s in self.products or not self.products:
                    return s, brand, 1.0, "sku"
        a = self._exact.get(_norm(name))
        if a:
            return a.sku, a.brand or brand, a.confidence, "alias"
        fk = extract(name).key()
        cands = self._fkey.get(fk)
        if cands and fk != "other":
            best = max(cands, key=cands.get)
            share = cands[best] / sum(cands.values())
            if share >= 0.6:
                return best, brand, round(0.5 * share, 2), "fkey"
        return None, brand, 0.0, "none"
