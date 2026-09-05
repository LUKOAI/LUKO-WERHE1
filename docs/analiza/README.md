# Analizy historii wysyłek FBA (2020-09 … 2026-08)

Dane: 72 pliki planów wysyłki z Google Drive (docx 2020–01.2022, xlsx 02.2022–06.2026, PDF z Apilo 07–08.2026) → 4 192 wysyłki, 10 741 pozycji, 209 641 sztuk. Zaimportowane do `data/history/` (100 % pozycji zmapowanych na SKU przez `data/product_aliases.csv`).

| Raport | Treść |
|---|---|
| `fc_rules.md` | co decyduje o magazynie WRO5 vs XPO1: reguła długości z podregułami szarej strefy, dokładność 99,29 % pozycji / 99,58 % sztuk, stabilność kwartalna, wyjątki per listing, reżim niemiecki |
| `composition.md` | wielkość i skład wysyłek, rekonstrukcja planów, moduły kartonów per produkt, produkty „solo” i „dopełniacze”, palety 07–08.2026 linia po linii, sezonowość |
| `name_fc_lookup.csv` | 886 nazw listingów z reżimu polskiego → dominujący FC, czystość, ostatni FC |

## Najważniejsze ustalenia

1. **Magazyn = klasa rozmiaru produktu.** Najdłuższy bok ≥ 46 cm → XPO1 (non-sortable, 3PL ID Logistics), < 40 cm → WRO5 (sortable, Okmiany). Szara strefa 40–46 cm rozstrzyga się per ASIN (wymiary opakowania w katalogu Amazon), ale stałe podreguły pokrywają ją prawie w całości. Po zmapowaniu nazw na SKU: 233 z 237 SKU (≥ 5 pozycji od 06.2024) ma czystość ≥ 0,9; jedyny naprawdę mieszany to zestaw „35/50 × 410 Hex30” (0,63).
2. **Amazon dzieli plan po SKU, nie po ilościach**, i nigdy nie miesza klas w jednej wysyłce. Prognoza podziału planu = suma przewidywań per SKU. Tylko 2,7 % planów (39/1 465) było rozdzielonych między WRO5 i XPO1; w nich WRO5 dostawał medianę 74 % sztuk, XPO1 „resztkę” (mediana 21 szt.).
3. **Wielkości:** paczka do XPO1 ≈ 14 szt. jednego produktu (7–20), paczka do WRO5 ≈ 40 szt. (15–69, 1–5 produktów), paleta ≈ 150 szt. (126–174), 6 pozycji, 4 produkty, ~25 szt./pozycję. Palety: 19 z 22 do XPO1 (świdry + przedłużka 1000/5000 mm), 3 do WRO5 (wbijaki, dłuta HEX30, pobijaki). Pracownik zwykle tworzy jedną wysyłkę FBA na paczkę.
4. **Kartony zbiorcze** widoczne w ilościach na pozycjach: świdry wg średnicy 40→15, 50→14, 60→13 (SDS Max 12), 80→11, 100→10, 120→9, 150→7, 200→6; przedłużka 400 → 34, 750 SDS Max → 14, 1180 → 9, 1000 → 10/30, 5000 → 4; dłuto 75×600 SDS Max → 14; szypa 135×410 → 29; wiertło 40×600 → 7; smar → 100; nożyki T744D → 50. Narzędzie używa tych modułów, gdy katalog nie ma wpisanego kartonu (`fbaplan/catalog/cartons.py`).
5. **Rotacja i sezonowość:** ostatnie 12 mies. 46 960 szt. / 1 017 wysyłek (+28 % / +45 % r/r); świdry 32,5 % sztuk 2026; szczyt luty–czerwiec, dołek listopad–styczeń; świdry/przedłużki/adaptery wiosenne, pobijaki i dłuta z drugim szczytem jesienią, wbijaki do pali latem. Zimą trudno dopełnić paletę XPO1 świdrami.
6. **Naturalne dopełniacze** (nigdy solo): świdry SDS Ø100–150 (moduł 7–10), adapter 1/2-20UNF-M14, przedłużka M14 120, pobijaki 16,5/32,5 SDS Plus, groszkowniki, zawleczki, nożyki T744D. **Produkty główne** (zwykle jeden pełny karton = jedna paczka): przedłużka 400 (34), dłuto 75×600 SDS Max (14), świder 100×600 (20), pobijak 20,2×165 SDS Max (56), zestaw dłut SDS Plus 600 (10), przedłużka 750 SDS Max (14).

## Jak narzędzie z tego korzysta

* Predyktor FC (`fbaplan/predict/fc.py`): historia per SKU z wagą świeżości (półokres 12 mies., tylko od 06.2024) → reguła długości z podregułami → oznaczenie „niepewne” dla szarej strefy bez historii (nieproponowane jako dopełniacze). Na SKU z historią: 277/277 zgodności z większością; sama reguła bez historii: 271 z 272 SKU (jedyny błąd to wyjątek per ASIN 75×400 SDS Max WERKON → WRO5).
* Kalkulator wypełnienia: moduły kartonów z historii, gdy brak w katalogu.
* Rekomendator: filtruje kandydatów po tym samym FC (p ≥ 0,8), premiuje rotację, niski zapas, domknięcie warstwy palety i współwystępowanie.

## Co nie zostało zrobione / zweryfikowane

* Raport o rotacji i współwystępowaniu miał powstać osobno (agent przerwany limitem sesji) — kluczowe liczby są w `composition.md` §4 i §6, a narzędzie liczy rotację/afinność na bieżąco z `data/history/`.
* Niezależna weryfikacja `fc_rules.md` przez drugiego analityka nie została ukończona; zamiast niej wykonano kontrolę czystości per SKU po mapowaniu nazw (233/237 ≥ 0,9) i test reguły bez historii (271/272) — wyniki zgodne z raportem.
* Mapowanie 1 354 nazw na SKU: 203 wprost z Apilo, 471 przez agentów (chunki 1–5, bez drugiej weryfikacji), 680 regułowo z ręcznym przeglądem 431 nazw z reżimu polskiego (192 korekty). Nazwy sprzed 06.2024 mapowane regułowo bez przeglądu — mogą zawierać błędy, ale nie wpływają na predykcję FC (reżim niemiecki jest poza oknem).
