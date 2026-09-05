# FBA Plan — system planowania wysyłek do Amazon FBA (WERHE / WERKON)

Wersja projektu: 0.1 (2026-09). Dokument opisuje problem, dane, model, algorytmy i architekturę narzędzia `fbaplan`.

## 1. Problem

Dziś pracownik tworzy plan wysyłki w Seller Central ręcznie:

1. dodaje produkty (np. tyle, ile mieści jedna paleta lub jeden karton),
2. Amazon dzieli plan na 2+ wysyłek do różnych magazynów (FC),
3. podział jest nieopłacalny, bo paleta / karton do drugiego magazynu jest prawie pusty,
4. pracownik szuka innych produktów (mało w FBA, ale się sprzedają), dokłada je i sprawdza, czy Amazon pozwoli wysłać je w jednej palecie do jednego magazynu,
5. jeśli nie, próbuje kolejnych produktów, aż plan „się złoży”,
6. koszt: godziny pracy i przewoźnik opłacany za pustą przestrzeń.

Cele narzędzia:

- **szybciej** — plan składa się w minuty, a nie w godziny prób,
- **taniej** — wypełnienie palety / kartonu jak najbliżej 100 %, żeby koszt frachtu rozkładał się na jak najwięcej sztuk.

## 2. Co wiemy z danych historycznych (72 pliki, 2020-09 … 2026-08)

Dane: 4 192 wysyłki, 10 741 pozycji, 209 641 sztuk. Trzy epoki:

| Okres | Format | Nazwy produktów | Magazyny |
|---|---|---|---|
| 09.2020 – 01.2022 | docx | niemieckie tytuły listingów | brak w plikach |
| 02.2022 – 06.2026 | xlsx | niemieckie, od 2024 polskie (tłumaczenie maszynowe) | 06.2022–04.2024 Niemcy (HAJ1, DTM1/2, LEJ1/3, STR1, DUS2, XSC1…), od 06.2024 Polska: **WRO5** (Okmiany) i **XPO1** (ID Logistics, Nowa Niedrzwica) |
| 07–08.2026 | PDF z Apilo | krótkie nazwy + wewnętrzne SKU (203 kody) | WRO5 / XPO1, typ „Palety Amazon” / „Paczki FBA” |

Kluczowe obserwacje (reżim polski, od 06.2024, 1 864 wysyłki):

- **Magazyn docelowy jest niemal deterministyczny per produkt.** Po zmapowaniu 1 354 nazw historycznych na 465 kanonicznych SKU (`data/product_aliases.csv`, 100 % pozycji rozpoznanych) 233 z 237 SKU z ≥ 5 pozycjami trafia zawsze do tego samego FC (czystość ≥ 0,9). Decyduje **najdłuższy bok**: ≥ 46 cm → **XPO1** (non-sortable, 3PL ID Logistics), < 40 cm → **WRO5** (sortable, Okmiany); 40–46 cm zależy od opakowania danego ASIN-u, ale stałe podreguły (przedłużki 400 i dłuta HEX28 400 → WRO5; dłuta SDS 400–410, HEX30 410, szerokie szypy, świdry ×450 → XPO1) dają regule 99,3 % trafności na pozycjach. Granica pokrywa się z klasą „paczka standardowa” Amazona (45 × 34 × 26 cm / 11,9 kg).
- **Amazon dzieli plan po SKU** (nigdy ilości jednego SKU), nigdy nie miesza klas w jednej wysyłce; tylko 2,7 % planów było rozdzielonych między WRO5 i XPO1. Palety jadą prawie wyłącznie do XPO1 (19/22 w 07–08.2026).
- Wysyłki są małe: mediana 25–28 szt., p90 ≈ 135 szt.; mediana 1 pozycja. Paczka do XPO1 ≈ 14 szt. jednego produktu, do WRO5 ≈ 40 szt.; paleta ≈ 150 szt., 6 pozycji, 4 produkty. Pracownik zwykle tworzy jedną wysyłkę FBA na paczkę.
- Ilości na pozycjach są wielokrotnościami kartonów zbiorczych (świdry wg średnicy 15/14/13/11/10/9/7/6 szt., przedłużka 400 → 34 itd.) — narzędzie odtwarza moduły kartonów z historii, gdy katalog ich nie ma.

Szczegółowe analizy (reguły FC, kompozycja wysyłek, moduły kartonów, sezonowość) — patrz `docs/analiza/`.

## 3. Reguły Amazon istotne dla planera (EU / PL, stan 2026)

Zebrane w `docs/AMAZON_ZASADY.md`; skrót:

- **Karton** (SPD, LTL, FTL): maks. 63,5 cm każdy bok; wyjątek: karton z pojedynczą sztuką oversize dłuższą niż 63,5 cm. Maks. 23 kg (etykieta „ciężka paczka” > 15 kg). Min. 15,2 × 10 × 2,5 cm. Kartony ze sztukami standard-size nie mogą zawierać sztuk oversize (pakowane i kierowane osobno).
- **Paleta**: tylko EUR/CHEP 80 × 120 cm, maks. **180 cm** wysokości z paletą, maks. **500 kg** brutto, folia przezroczysta, brak nawisu poza obrys, 4 etykiety palety, **wszystkie sztuki na palecie z jednej wysyłki (jedno shipment ID)**. Piętrowanie palet tylko w wybranych FC (do 3,0 m).
- **Klasy rozmiaru** (waga objętościowa = L·W·H / 5000): mała paczka ≤ 35×25×12 cm / 3,9 kg; standard parcel ≤ 45×34×26 cm / 11,9 kg; small oversize ≤ 61×46×46 cm / 1,76 kg; standard oversize ≤ 120×60×60 cm / 29,76 kg; large oversize ≤ 150×60×60 / 31,5 kg; special oversize > 175 cm lub > 31,5 kg.
- **Podział na magazyny**: w EU nie ma (jak w USA) płatnej opcji „minimal splits” — Amazon dzieli plan wg własnego uznania. Wpływ mamy tylko przez skład planu (produkty, ilości, palety vs paczki). W SP-API (Fulfillment Inbound v2024-03-20) podział jest widoczny jako `PlacementOption` z listą wysyłek i `destination.warehouseId` **przed** potwierdzeniem — można więc symulować plan bez jego tworzenia „na ostro”.
- **Limity pojemności**: miesięczny limit w m³ per typ (standard / oversize); zużywany w momencie **utworzenia** wysyłki (także otwarte, niewysłane plany). Widoczny w Capacity Monitor.
- **Opłaty**: w EU brak opłaty placement; czynniki kosztowe to fracht (paleta / paczki), dopłata CEP (jeśli nie zezwolono na magazynowanie w PL/CZ), opłata za niski stan (Pan-EU).

## 4. Model danych

```
Product          — kanoniczny produkt fizyczny (SKU Apilo, np. 1WG80x800p)
  sku, name_pl, family, brand_variants[] (WERHE/WERKON = osobne listingi Amazon: msku)
  unit: length_cm, width_cm, height_cm, weight_kg  (w opakowaniu jednostkowym)
  carton: units_per_carton, length_cm, width_cm, height_cm, weight_kg  (karton zbiorczy)
  size_tier (wyliczana), oversize (bool), fc_override (opcjonalnie ręcznie)
  pack_group (np. "długie", "małe") — produkty z różnych grup nie pakuje się razem
  max_qty_per_plan, active
Alias            — nazwa z historii / listingu → sku (+ brand)
HistoryShipment  — zaimportowana wysyłka (data, FC, typ, pozycje: sku, qty)
Verdict          — zapis decyzji Amazona dla planu (sku → FC, data) — zasila predyktor
StockSnapshot    — stan FBA i sprzedaż per msku (import z raportów Seller Central)
Plan             — sesja planowania: tryb (paleta / paczki), pozycje, ograniczenia, wynik
```

Pliki: `data/products.csv`, `data/product_aliases.csv`, `data/history/*.csv`, `data/verdicts.csv`, `data/stock.csv`, `data/planner_params.json`; sesje planów w `data/plans/*.json`.

## 5. Algorytmy

### 5.1 Predyktor magazynu (FC)

Dla każdego SKU: rozkład prawdopodobieństwa FC z trzech źródeł, w kolejności zaufania:

1. **Nadpisanie ręczne** (`fc_override`).
2. **Historia** (import + werdykty): ważony udział FC, waga = 0,5^(miesiące_temu / 12) (świeższe ważniejsze), liczone tylko w reżimie polskim (od 06.2024). Wymagane min. 3 obserwacje (parametr).
3. **Reguła fizyczna** z wymiarów: jeśli sztuka mieści się w „standard parcel” (≤ 45×34×26 cm i ≤ 11,9 kg) → sortable → WRO5; inaczej → non-sortable → XPO1. Gdy brak wymiarów — reguła rodzinowa z nazwy (świdry, dłuta ≥ 450 mm → XPO1; adaptery, nożyki, pobijaki, przedłużki ≤ 400 mm → WRO5).

Wynik: `{WRO5: p, XPO1: p, inne: p}`, pewność, źródło i dowody (liczba wysyłek, ostatnia data). Parametry w `planner_params.json` (uczone z analizy historii).

### 5.2 Kalkulator wypełnienia

- Wejście: pozycje (sku, qty) → kartony: pełne kartony zbiorcze per SKU + karton mieszany na resztki (jeśli dozwolone).
- Walidacja kartonów wg limitów Amazon (bok, waga; wyjątek dla pojedynczych długich sztuk).
- Paleta: warstwowanie kartonów o tym samym obrysie na 80 × 120 cm (obie orientacje), wysokość ładunku ≤ 180 − 15 cm palety, masa ≤ 500 kg. Wypełnienie = objętość kartonów / objętość dostępna; osobno „ile jeszcze kartonów o obrysie X wejdzie”.
- Tryb paczek: liczba paczek, wypełnienie każdej, koszt/szt. przy podanej stawce przewoźnika.

### 5.3 Rekomendacja dopełniaczy (filler)

Kandydat = aktywny produkt, którego przewidywany FC zgadza się z FC kotwicy planu (p ≥ próg), zgodny z grupą pakowania, nie wykluczony przez użytkownika.

Ocena: `score = w_fc·p(FC) + w_sales·rotacja + w_stock·(1 − pokrycie/cel) + w_fit·dopasowanie_do_wolnego_miejsca`, gdzie rotacja i pokrycie z `stock.csv` (sprzedaż 30/90 dni, stan FBA + w drodze), a dopasowanie premiuje produkty, których pełne kartony domykają warstwę palety. Sugerowana ilość = wielokrotność kartonu, maks. do `max_qty_per_plan` i do wolnej pojemności (m³) konta.

### 5.4 Automatyczne dopełnianie

`planner/autofill.py`: pętla „oceń plan → dodaj pełny karton najlepszego kandydata → oceń ponownie”. Najpierw do 8 nowych dopełniaczy (różnorodność, wg oceny rekomendatora), potem uzupełnianie produktów już w planie (wg rotacji), aż ostatnia paleta magazynu głównego osiągnie zadane wypełnienie objętości (domyślnie 90 %) lub, bez wymiarów, zadaną liczbę sztuk. Dodanie, które przelewa paletę poza limit, jest cofane. Wynik jest zwykłym planem — użytkownik może go dowolnie poprawić.

### 5.5 Pętla z werdyktem Amazona

1. Użytkownik składa plan w narzędziu → widzi przewidywany podział na FC, wypełnienie, listę pakowania.
2. Tworzy plan w Seller Central (lub, docelowo, narzędzie robi to przez SP-API i czyta `PlacementOption` bez potwierdzania).
3. Wpisuje faktyczny podział Amazona (sku → FC). Narzędzie zapisuje werdykt (uczy predyktor) i proponuje korekty: usunąć/przenieść pozycje z „mniejszościowego” FC albo dopełnić drugą paletę.
4. Eksport: lista pozycji do Send to Amazon, lista pakowania per karton / paleta, podsumowanie.

## 6. Architektura

```
fbaplan/
  models.py        dataclasses + serializacja
  rules/amazon.py  stałe i walidacje (karton, paleta, klasy rozmiaru)
  catalog/         normalize.py (ekstrakcja cech z nazw), store.py (produkty, aliasy)
  history/         parsers.py (docx/xlsx/pdf), store.py (import, statystyki)
  predict/fc.py    predyktor FC
  packing/fill.py  kartony, palety, wypełnienie
  planner/         session.py (plan, werdykty), filler.py (rekomendacje), autofill.py
  imports.py       raporty Seller Central (Podgląd opłat, zapasy FBA, Uzupełnij zapasy), katalog XLSX
  export.py        CSV / XLSX / HTML do druku
  cli.py           polecenia: import-history, build-catalog, predict, plan, suggest, serve
  web/             FastAPI + szablony (PL), lokalnie na http://127.0.0.1:8765
  spapi/           adapter SP-API (interfejs + implementacja symulacji placement options; wymaga kluczy)
tests/             pytest
data/              katalog, aliasy, historia, parametry
docs/              projekt, zasady Amazon, instrukcja, analizy
```

Uruchomienie na Windows: `run_fbaplan.ps1` (tworzy venv, instaluje zależności, startuje UI). Dane w plikach CSV/JSON — łatwe do edycji w Excelu.

## 7. Czego brakuje w danych i co musi dostarczyć klient

1. **Wymiary i wagi** sztuk w opakowaniu oraz kartonów zbiorczych (ile sztuk w kartonie) — najprościej eksport „Podgląd opłat / Fee preview” z Seller Central (ma wymiary i klasę rozmiaru per SKU) + tabela kartonów z magazynu. Szablon: `data/products.csv`.
2. **Stan FBA i sprzedaż** — raporty „Manage FBA Inventory” i „Restock Inventory” (kolumny: available, inbound, sales 30/90 dni). Szablon: `data/stock.csv`.
3. **Ograniczenia pakowania** — których produktów nie wolno łączyć w kartonie / na palecie, limity ilości per plan.
4. **Stawki frachtu** (paleta, paczka) — do liczenia kosztu/szt.
5. Opcjonalnie: dostęp SP-API (aplikacja deweloperska, refresh token) — wtedy narzędzie samo symuluje podział Amazona.

## 8. Ryzyka

- Amazon może zmienić sieć FC lub logikę podziału (jak w 2024: Niemcy → Polska). Predyktor waży świeżość i uczy się z werdyktów, ale pierwsza zmiana zawsze zaskoczy.
- Historia nie zawiera wymiarów ani przyczyn decyzji Amazona; reguła fizyczna jest hipotezą potwierdzoną empirycznie (czystość 0,95), nie dokumentacją Amazona.
- Nazwy w historii są zmienne (DE → PL → Apilo); mapowanie na SKU jest częściowo automatyczne i wymaga przeglądu (`data/product_aliases.csv`, kolumna `confidence`).
