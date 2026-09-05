# FBA Plan — instrukcja użytkownika

Narzędzie pomaga ułożyć plan wysyłki do Amazon FBA tak, żeby (1) Amazon nie podzielił go na dwa magazyny i (2) paleta lub karton były jak najpełniejsze.

## 1. Uruchomienie (Windows)

1. Zainstaluj Python 3.11 lub nowszy (zaznacz „Add python.exe to PATH”).
2. Kliknij dwukrotnie `run_fbaplan.bat`. Pierwsze uruchomienie instaluje zależności (1–2 min). Otworzy się przeglądarka z adresem `http://127.0.0.1:8765`.
3. Zamknięcie okna konsoli zatrzymuje program. Dane są w katalogu `data/` (pliki CSV/JSON — kopia zapasowa = skopiowanie katalogu).

Wiersz poleceń (alternatywa): `python -m fbaplan serve --open`, `python -m fbaplan plan 1WG80x800p=40 --suggest 10`, `python -m fbaplan predict`, `python -m fbaplan stats`.

## 2. Dane, które trzeba uzupełnić

| Plik | Co zawiera | Skąd wziąć |
|---|---|---|
| `data/products.csv` | katalog produktów: SKU, nazwa, rodzina, marki, SKU sprzedawcy Amazon (WERHE / WERKON), **wymiary i waga sztuki w opakowaniu**, **ile sztuk w kartonie zbiorczym i wymiary kartonu**, ręczne przypisanie magazynu, grupa pakowania, limit ilości w planie | 203 SKU z Apilo są już wpisane. Wymiary: Seller Central → Raporty → „Podgląd opłat” (Fee preview) ma wymiary i wagę per SKU; kartony — z magazynu |
| `data/stock.csv` | stan FBA (dostępne, w drodze), sprzedaż 30/90 dni, stan własny — per SKU sprzedawcy | Seller Central → Zapasy → „Zarządzaj zapasami FBA” (eksport) i raport „Uzupełnij zapasy”; można wkleić kolumny do szablonu (`python -m fbaplan stock-template`) |
| `data/product_aliases.csv` | nazwy historyczne (tytuły listingów DE/PL) → SKU | wygenerowane z historii; można poprawiać |
| `data/history/` | historia wysyłek 2020–2026 (po imporcie) | `python -m fbaplan import-history --src KATALOG_Z_PLIKAMI` |
| `data/verdicts.csv` | decyzje Amazona zapisane w narzędziu | powstaje automatycznie |
| `data/planner_params.json` | stawki frachtu, wolny limit pojemności, wagi propozycji, limity Amazon | zakładka **Ustawienia** |

Bez wymiarów sztuki narzędzie przewidzi magazyn (z historii i z nazwy), ale nie policzy wypełnienia palety. Bez `stock.csv` propozycje dopełnienia opierają się tylko na historii wysyłek.

## 3. Praca z planem

1. **Plany → Nowy plan**: tryb *paleta* lub *paczki*, opcjonalnie magazyn docelowy i maks. liczba palet.
2. **Dodaj produkt główny** (SKU z listy, ilość — domyślnie pełny karton). Narzędzie pokazuje:
   * przewidywany magazyn dla każdej pozycji (WRO5 = drobne, „sortable”; XPO1 = długie, „oversize”) z wyjaśnieniem i pewnością,
   * **magazyn główny** planu (ten, który zajmuje najwięcej miejsca) i ostrzeżenie, jeśli plan zostanie podzielony,
   * dla trybu paleta: liczbę palet, wysokość ładunku, masę, wypełnienie objętości i wysokości, układ warstw,
   * ostrzeżenia: karton ponad limit Amazon (63,5 cm / 23 kg), paleta ponad 180 cm / 500 kg, ilość poza pełnym kartonem, brak wymiarów, przekroczony limit pojemności.
3. **Propozycje dopełnienia**: lista produktów, które (a) prawie na pewno trafią do tego samego magazynu, (b) sprzedają się i mają niski zapas w FBA, (c) mieszczą się na ostatniej palecie (pełne kartony). Kliknij **dodaj** (ilość można zmienić) albo **ukryj**, jeśli danego produktu nie chcesz wysyłać. Ocena = suma wag z Ustawień; kolumna „Uzasadnienie” mówi dlaczego.
4. **Eksport**: „CSV do Send to Amazon” (SKU sprzedawcy + ilość; przy planie dzielonym osobny CSV per magazyn) i XLSX (pozycje, lista pakowania per karton/warstwa/paleta, podsumowanie palet).
5. **Utwórz plan w Seller Central** tak jak dotąd. Zobacz, jak Amazon podzielił wysyłkę.
6. **Zapisz decyzję Amazona** (sekcja „Decyzja Amazona”): wpisz faktyczny magazyn dla każdej pozycji. Narzędzie zapisuje to w `data/verdicts.csv` i od razu poprawia przewidywania. Jeśli Amazon zdecydował inaczej niż przewidziano, pokaże, które pozycje przenieść do osobnego planu.
7. Status planu: szkic → złożony w SC → werdykt zapisany → zamknięty. „Kopiuj” tworzy nowy plan z tymi samymi pozycjami.

## 4. Zasady, które narzędzie stosuje (z historii 2024–2026)

* **Amazon dzieli plan po produktach, nigdy ilość jednego SKU na dwa magazyny** i nigdy nie miesza w jednej wysyłce produktów „krótkich” (< 40 cm) i „długich” (≥ 46 cm).
* Produkty o najdłuższym boku **≥ 46 cm** → XPO1; **< 40 cm** → WRO5; 40–46 cm zależy od opakowania zarejestrowanego w Amazon dla danego ASIN-u (przedłużki 400, dłuta HEX28 400, szpadel 75×410 HEX30, świder 80×450 → WRO5; dłuta SDS 400–410, HEX30 410, szerokie szypy, świdry ×450 → XPO1). Trafność reguły na historii: 99,3 % pozycji. Historia konkretnego SKU ma pierwszeństwo przed regułą.
* Nowe, długie produkty przy pierwszej wysyłce bywają kierowane jak „krótkie” (do WRO5) — po zmierzeniu w magazynie klasa się zmienia. Produkty z szarej strefy bez historii są oznaczone jako niepewne i nie są proponowane jako dopełniacze.
* Typowe wielkości: paczka do XPO1 ≈ 14 szt. jednego produktu, paczka do WRO5 ≈ 40 szt. (1–5 produktów), paleta ≈ 150 szt., 6 pozycji, 4 produkty; palety jadą prawie wyłącznie do XPO1 (świdry + przedłużki 1000/5000 mm).
* Kartony zbiorcze (gdy nie wpisano w katalogu, narzędzie zakłada z historii): świdry wg średnicy 40→15, 50→14, 60→13 (SDS Max 12), 80→11, 100→10, 120→9, 150→7, 200→6 szt.; przedłużka 400 mm → 34, 750 SDS Max → 14, 1180 → 9, 1000 → 10 (SDS Max) / 30 (do świdra), 5000 → 4; dłuto 75×600 SDS Max → 14, 110×410 → 7, szypa 135×410 → 29; wiertło 40×600 → 7; smar → 100; nożyki T744D 5 szt. → 50.

## 5. Limity Amazon (EU, 2026)

* Karton: każdy bok ≤ 63,5 cm (wyjątek: jedna sztuka oversize dłuższa niż 63,5 cm), ≤ 23 kg (etykieta „ciężka paczka” > 15 kg), minimum 15,2 × 10 × 2,5 cm. Karton ze sztukami standard-size nie może zawierać sztuk oversize.
* Paleta: EUR/CHEP 80 × 120 cm, ≤ 180 cm z paletą, ≤ 500 kg brutto, folia przezroczysta, 4 etykiety, wszystkie kartony z jednej wysyłki (jedno shipment ID).
* Limit pojemności FBA (m³, standard / oversize) jest zużywany w momencie utworzenia wysyłki — niepotrzebne plany anulować.

## 6. Utrzymanie

* Nowe miesiące historii: dopisz pliki (xlsx z Seller Central lub PDF z Apilo) do katalogu i uruchom `python -m fbaplan import-history --src KATALOG`, potem „Przeładuj dane”.
* Nowy produkt: **Katalog → Dodaj produkt** (SKU wg konwencji Apilo, np. `1WG60x800p`), uzupełnij wymiary i karton.
* Zmiana sieci magazynów Amazon: w `data/planner_params.json` → `predictor` ustaw `regime_start` na datę zmiany i kody `sortable_fc` / `nonsortable_fc` / `known_fcs`; stare werdykty przestaną być brane pod uwagę.
