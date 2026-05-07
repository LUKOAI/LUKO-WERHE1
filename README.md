# WERHE/WERKON - Generator PDF dla urzedu skarbowego

Desktopowa aplikacja (Python + CustomTkinter), ktora automatyzuje przygotowanie dokumentow do wydruku:
- pobiera zamowienia z Apilo API (OAuth),
- filtruje kwalifikujace sie pozycje (poza UE + faktura `.pl` + tracking),
- robi screenshot potwierdzenia doreczenia przez Playwright,
- generuje PDF per zamowienie + podsumowanie PDF + podsumowanie Excel.

## 1) Wymagania

- Windows 10/11 (docelowo pod `.exe`)
- Python 3.11+
- Dostep do Internetu
- Dane z panelu Apilo: **Client ID**, **Client Secret**, **Kod autoryzacji**

## 2) Instalacja (tryb developerski)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

### Gdzie uruchamiac (wazne na Windows)

Nie uruchamiaj projektu z `C:\Windows\System32`.

Uzyj katalogu roboczego, np.: `C:\Users\MASTER\Desktop\Do pana paczesnego\2026`.

## 3) Konfiguracja

### Sposob 1: Przez GUI (zalecany)

1. Uruchom `python main.py`.
2. Wpisz **Client ID**, **Client Secret** i **Kod autoryzacji** z panelu Apilo.
3. Kliknij **Polacz z Apilo** — aplikacja sama uzyska access_token.
4. Token jest wazny 21 dni i odswiezy sie automatycznie.

### Sposob 2: Reczna edycja config.json

1. Skopiuj `config.example.json` do `config.json`.
2. Uzupelnij pola: `apilo_client_id`, `apilo_client_secret`, `apilo_auth_code`.
3. Uruchom aplikacje i kliknij **Polacz z Apilo**.

### Skad wziac dane z Apilo?

W panelu Apilo przejdz do: **Ustawienia > Klucze API Apilo**
Znajdziesz tam:
- **Client ID** (identyfikator klienta)
- **Client Secret** (klucz tajny)
- **Kod autoryzacji** (authorization code)

## 4) Uruchomienie

```bash
python main.py
```

W GUI:
1. Wpisz dane Apilo i kliknij **Polacz z Apilo**.
2. Wybierz zakres dat `YYYY-MM-DD`.
3. (Opcjonalnie) wpisz numery zamowien:
   - **Numery Apilo** (`order_number`/`order_id`) rozdzielone przecinkami,
   - **Numery Amazon** rozdzielone przecinkami.
4. Kliknij **Generuj PDF-y** albo **Test na 5 zamowieniach**.

## 5) Wyniki

Pliki pojawiaja sie w katalogu:

```text
<output_root>/PDFy_YYYY_MM/
np. C:\Users\MASTER\Desktop\Do pana paczesnego\2026\WERHE_PDFy\PDFy_2026_03\
```

Struktura:
- `_screenshots/` - screenshoty trackingu,
- `zamowienia/` - pojedyncze PDF-y zamowien,
- `podsumowanie.pdf` - zestawienie zbiorcze,
- `podsumowanie.xlsx` - tabela pomocnicza.

## 6) Logi i bledy

- Log aplikacji: `logs/app.log`
- Aplikacja przetwarza zamowienia niezaleznie - blad jednego zamowienia nie przerywa calego procesu.
- Jesli tracking nie zawiera rozpoznawalnego statusu doreczenia, aplikacja robi fallback do full-page screenshota.

## 7) Build .exe

Uzyj `build_exe.bat` lub recznie:

```bash
pyinstaller --noconfirm --onefile --windowed --name WerhePdfTool main.py
```

Po buildzie plik `.exe` bedzie w `dist/`.

## 8) Roznice FBA/FBC vs magazyn wlasny

- Zamowienia sa rozdzielane po polu `warehouse_type` (`fba` vs inne).
- W podsumowaniu PDF tworzone sa osobne sekcje.

## 9) Wazne uwagi biznesowe

- IE599/CC599 pozostaje reczne (zgodnie z wymaganiami).
- Urzad wymaga dokumentow papierowych - aplikacja optymalizuje przygotowanie materialu do druku.

## 10) Jak dziala autentykacja Apilo (OAuth)

1. Aplikacja wysyla POST na `/rest/auth/token/` z Basic Auth (Client ID + Client Secret)
   i kodem autoryzacji.
2. Apilo zwraca `accessToken` (wazny 21 dni) i `refreshToken`.
3. `accessToken` jest uzywany jako Bearer token do wszystkich wywolan API.
4. Gdy token wygasa, aplikacja automatycznie go odswiezy uzywajac `refreshToken`.
5. Tokeny sa zapisywane w `config.json` (nie wysylaj tego pliku nikomu!).
