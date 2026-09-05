"""FBA stock and sales snapshot (``data/stock.csv``).

Columns (header names are matched case-insensitively, Polish and Seller
Central English variants accepted):

    sku | msku | brand | fba_available | fba_inbound | sales_30d | sales_90d | local_stock

Rows are aggregated per canonical SKU (WERHE + WERKON listings of the same
physical product are summed). Merchant SKUs are mapped to canonical SKUs via
the catalog (``mskus``) or an alias.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from .models import Product, StockRow

COLUMN_ALIASES = {
    "sku": ["sku", "kanoniczny", "canonical_sku"],
    "msku": ["msku", "merchant sku", "seller-sku", "seller_sku", "sku sprzedawcy"],
    "brand": ["brand", "marka"],
    "fba_available": ["fba_available", "available", "afn-fulfillable-quantity", "dostępne", "dostepne", "stan fba"],
    "fba_inbound": ["fba_inbound", "inbound", "afn-inbound-shipped-quantity", "w drodze", "inbound quantity"],
    "sales_30d": ["sales_30d", "units sold last 30 days", "sprzedaż 30", "sprzedaz 30", "sold_30d"],
    "sales_90d": ["sales_90d", "units sold last 90 days", "sprzedaż 90", "sprzedaz 90", "sold_90d"],
    "local_stock": ["local_stock", "stan własny", "stan wlasny", "magazyn", "own_stock"],
}


def _pick(row: dict, key: str) -> Optional[str]:
    low = {k.strip().lower(): v for k, v in row.items() if k}
    for cand in COLUMN_ALIASES[key]:
        if cand in low and low[cand] not in (None, ""):
            return low[cand]
    return None


def _int(v: Optional[str]) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(float(str(v).replace(",", ".").replace(" ", "")))
    except ValueError:
        return 0


def load_stock(path: Path | str, products: dict[str, Product]) -> dict[str, StockRow]:
    path = Path(path)
    if not path.exists():
        return {}
    msku_map = {m: p.sku for p in products.values() for m in p.mskus.values()}
    out: dict[str, StockRow] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample else csv.excel
        for r in csv.DictReader(fh, dialect=dialect):
            sku = (_pick(r, "sku") or "").strip()
            msku = (_pick(r, "msku") or "").strip()
            if not sku and msku:
                sku = msku_map.get(msku, "")
            if not sku:
                continue
            row = out.setdefault(sku, StockRow(sku, msku, _pick(r, "brand") or ""))
            row.fba_available += _int(_pick(r, "fba_available"))
            row.fba_inbound += _int(_pick(r, "fba_inbound"))
            row.sales_30d += _int(_pick(r, "sales_30d"))
            row.sales_90d += _int(_pick(r, "sales_90d"))
            ls = _pick(r, "local_stock")
            if ls not in (None, ""):
                row.local_stock = (row.local_stock or 0) + _int(ls)
    return out


def save_stock_template(path: Path | str, products: dict[str, Product]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["sku", "msku", "brand", "fba_available", "fba_inbound", "sales_30d", "sales_90d", "local_stock"])
        for p in sorted(products.values(), key=lambda p: p.sku):
            if p.mskus:
                for b, m in p.mskus.items():
                    w.writerow([p.sku, m, b, "", "", "", "", ""])
            else:
                w.writerow([p.sku, "", "", "", "", "", "", ""])
