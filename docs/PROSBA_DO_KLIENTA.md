# Dane potrzebne do uruchomienia FBA Plan — lista dla WERHE

Narzędzie jest gotowe i ma już wczytaną całą historię wysyłek (2020–2026). Żeby liczyło wypełnienie palety i proponowało dopełniacze według sprzedaży, potrzebuje jeszcze poniższych danych. Kolejność wg ważności.

## 1. Wymiary i wagi produktów (najważniejsze)

**Najprościej — raport z Seller Central:** Raporty → Realizacja (Fulfillment) → sekcja „Płatności” / „Opłaty” → **„Podgląd opłat” (Fee Preview)** → „Zażądaj pobrania” → plik .txt. Zawiera dla każdego SKU Amazon: najdłuższy / średni / najkrótszy bok, wagę opakowania i klasę rozmiaru. Ten plik wystarczy wczytać w narzędziu (Import → „Podgląd opłat”).

Jeśli raport jest niedostępny: w arkuszu `katalog_do_uzupelnienia.xlsx` (zakładka Import → „Pobierz katalog do uzupełnienia”) wpisać wymiary sztuki w opakowaniu (cm) i wagę (kg). Arkusz jest posortowany od najczęściej wysyłanych produktów — wystarczy wypełnić pierwsze 80–100 wierszy, żeby pokryć ~90 % wysyłek.

## 2. Kartony zbiorcze

Dla każdego produktu: **ile sztuk w kartonie zbiorczym** oraz wymiary (cm) i waga kartonu (kg). Narzędzie odgadło liczbę sztuk z historii (np. świder 80 mm SDS Plus — 11 szt., przedłużka 400 mm — 34 szt., dłuto 75×600 SDS Max — 14 szt.) — niebieskie pola w arkuszu do potwierdzenia. Wymiary kartonu są konieczne do ułożenia palety; bez nich narzędzie szacuje je z wymiarów sztuki.

## 3. Stan magazynu FBA i sprzedaż

Dwa raporty z Seller Central (oba wczytuje zakładka Import → „Stan FBA i sprzedaż”):

- **„Zarządzaj zapasami FBA”** (Zapasy → Zarządzaj zapasami FBA → Pobierz): dostępne i w drodze per SKU.
- **„Uzupełnij zapasy”** (Zapasy → Uzupełnij zapasy / Restock Inventory → Pobierz): sprzedaż z 30 dni, dni zapasu, rekomendacje.

Odświeżać przed każdą sesją planowania (raz w tygodniu wystarczy).

## 4. Ograniczenia pakowania (krótka rozmowa z magazynem)

- Których produktów **nie wolno pakować razem** w kartonie / na palecie (np. długie z drobnymi)? Narzędzie ma pole „grupa pakowania”.
- Czy są produkty, których **nie chcecie wysyłać więcej niż X szt. na plan** (pole „Maks. szt. w planie”)?
- Czy paleta może być wyższa niż 180 cm (Amazon: maks. 180 cm z paletą, 500 kg)?

## 5. Koszty frachtu

Orientacyjny koszt palety do XPO1 / WRO5 i koszt paczki (zł) — do wyliczenia kosztu na sztukę (Ustawienia).

## 6. Do potwierdzenia w Seller Central (zrzuty ekranu)

- Krok 2 „Potwierdź wysyłkę” w Send to Amazon — czy są tam do wyboru opcje podziału (jak w USA), czy tylko jeden podział Amazona.
- **Capacity Monitor** (dół pulpitu FBA): wolny limit pojemności w m³ dla standard i oversize — do wpisania w Ustawieniach.
- Czy zestaw „35/50 × 410 Hex30” ma dwa ASIN-y (w historii raz szedł do WRO5, raz do XPO1).

## 7. Opcjonalnie: SP-API

Jeśli chcecie, żeby narzędzie samo sprawdzało podział Amazona przed utworzeniem planu: aplikacja deweloperska w Seller Central (rola „Amazon Fulfillment”) i refresh token. Bez tego narzędzie działa na historii i regułach.

---

Po dostarczeniu punktów 1–3 narzędzie od razu: przewiduje magazyn dla każdego produktu, liczy palety i proponuje dopełnienie („Dopełnij automatycznie”). Pierwsze 2–3 tygodnie: po każdym planie w Seller Central wpisać w narzędziu faktyczny podział Amazona (zakładka planu → „Decyzja Amazona”) — to poprawia przewidywania dla nowych produktów.
