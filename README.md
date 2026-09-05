# LUKO-WERHE1 — FBA Plan

Narzędzie do planowania wysyłek do Amazon FBA dla WERHE / WERKON: przewiduje, do którego magazynu Amazon skieruje każdy produkt (WRO5 vs XPO1), liczy wypełnienie palety / kartonów i proponuje produkty do dopełnienia wysyłki tak, żeby plan nie został podzielony na dwa magazyny.

## Szybki start (Windows)

1. Zainstaluj Python 3.11+ (z opcją „Add to PATH”).
2. Uruchom `run_fbaplan.bat` — otworzy się `http://127.0.0.1:8765`.

Wiersz poleceń: `python -m fbaplan serve --open` (UI), `python -m fbaplan plan 1ZWG80dp=33 --suggest 10 --autofill`, `predict`, `stats`, `import-history --src KATALOG`, `import-fee-preview PLIK`, `import-stock PLIK...`, `export-catalog`, `import-catalog PLIK.xlsx`.

## Dokumentacja

| Plik | Treść |
|---|---|
| `docs/INSTRUKCJA.md` | instrukcja użytkownika: dane do uzupełnienia, praca z planem, zasady |
| `docs/PROJEKT.md` | projekt systemu: problem, dane, model, algorytmy, architektura |
| `docs/AMAZON_ZASADY.md` | reguły Amazon FBA (EU/PL) istotne dla planera, z poziomem pewności |
| `docs/analiza/` | analizy historii 2020–2026: reguły FC, kompozycja wysyłek, rotacja |
| `docs/PROSBA_DO_KLIENTA.md` | lista danych do pozyskania od klienta (raporty Seller Central, kartony, ograniczenia) |

## Dane (`data/`)

- `products.csv` — katalog (465 SKU: 203 z Apilo + 262 historycznych); **wymiary i kartony do uzupełnienia** (arkusz `katalog_do_uzupelnienia.xlsx`)
- `product_aliases.csv` — 1 354 nazwy historyczne → SKU
- `history/` — 4 192 wysyłki / 10 741 pozycji 2020-09 … 2026-08 (zaimportowane)
- `stock.csv` — stan FBA i sprzedaż (do dostarczenia; `python -m fbaplan stock-template`)
- `verdicts.csv` — decyzje Amazona zapisane w narzędziu
- `planner_params.json` — parametry

## Struktura kodu

```
fbaplan/            pakiet narzędzia (silnik + CLI + UI)
  rules/amazon.py   limity Amazon (karton, paleta, klasy rozmiaru)
  predict/fc.py     predyktor magazynu
  packing/fill.py   kartony, palety, wypełnienie
  planner/          ocena planu, dopełniacze, werdykty
  catalog/, history/, stock.py, imports.py (raporty Seller Central), export.py, context.py, cli.py, web/
  spapi/            adapter SP-API (symulacja podziału; wymaga kluczy)
tests/              pytest (17 testów)
main.py             stara aplikacja demonstracyjna (customtkinter), niezależna od fbaplan
```

Testy: `python -m pytest -q tests`.
