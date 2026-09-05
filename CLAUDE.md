# LUKO-WERHE1 — notes for coding agents

Polish-language tool (`fbaplan/`) that plans Amazon FBA inbound shipments for WERHE/WERKON:
predicts the destination warehouse per SKU (WRO5 = sortable, XPO1 = non-sortable), packs
cartons onto EUR pallets, recommends filler products, records Amazon's verdicts.

## Commands

- Tests: `python -m pytest -q tests` (all must pass before committing).
- Web UI: `python -m fbaplan serve --open` (FastAPI + Jinja2, http://127.0.0.1:8765).
- CLI: `python -m fbaplan --help` (plan, predict, stats, import-history, import-fee-preview, import-stock, export-catalog, import-catalog, verdict).
- Dependencies: `requirements.txt` (fastapi, uvicorn, jinja2, python-multipart, openpyxl, python-docx, pdfplumber, pytest).

## Layout

- `fbaplan/rules/amazon.py` — EU box/pallet limits, size tiers (numbers documented in `docs/AMAZON_ZASADY.md`).
- `fbaplan/predict/fc.py` — FC predictor: override → recency-weighted history (regime from 2024-06) → length rule (≥460 mm non-sortable, <400 sortable, grey-zone sub-rules from `docs/analiza/fc_rules.md`).
- `fbaplan/packing/fill.py` — cartons, layer-based pallet packing, utilisation.
- `fbaplan/planner/` — `session.evaluate` (plan → FC groups, warnings), `filler.suggest`, `autofill.autofill`, verdicts.
- `fbaplan/catalog/` — `normalize.extract` (features from DE/PL/Apilo product names), `store.Resolver` (name → SKU), `cartons.py` (carton modules inferred from history).
- `fbaplan/history/` — parsers for the client's docx/xlsx/Apilo-pdf shipment plans, history store + stats.
- `fbaplan/imports.py` — Seller Central report importers (fee preview, inventory/restock) and catalog XLSX round trip.
- `fbaplan/web/` — routes in `app.py`, templates in `templates/` (Polish UI text).
- `data/` — `products.csv` (canonical SKUs, Apilo codes), `product_aliases.csv` (historical titles → SKU), `history/` (imported shipments), `stock.csv`, `verdicts.csv`, `planner_params.json`.
- `docs/` — PROJEKT (design), INSTRUKCJA (user manual), AMAZON_ZASADY (rules), PROSBA_DO_KLIENTA (data request), `analiza/` (history analyses).
- `main.py` — legacy customtkinter demo, unrelated to `fbaplan`.

## Conventions

- All user-facing strings in Polish; code identifiers and comments in English.
- Dimensions in cm, weights in kg, lengths from product names in mm.
- Canonical SKU = physical product (Apilo code convention: family digit + letters + dims + shank suffix p/m/h28/h30); WERHE vs WERKON are brand variants (`mskus`).
- Never invent product dimensions into `products.csv`; estimates live in `CartonSpec.estimated` / notes.
- Keep `data/product_aliases.csv` and `data/products.csv` consistent (test `test_repo_catalog_and_aliases_consistent`).
