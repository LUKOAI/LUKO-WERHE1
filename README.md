# WERHE/WERKON – Generator PDF dla urzędu skarbowego

Desktopowa aplikacja (Python + CustomTkinter), która automatyzuje przygotowanie dokumentów do wydruku:
- pobiera zamówienia z Apilo API,
- filtruje kwalifikujące się pozycje (poza UE + faktura `.pl` + tracking),
- robi screenshot potwierdzenia doręczenia przez Playwright,
- generuje PDF per zamówienie + podsumowanie PDF + podsumowanie Excel.

## 1) Wymagania

- Windows 10/11 (docelowo pod `.exe`)
- Python 3.11+
- Dostęp do Internetu
- Bearer token do Apilo API

## 2) Instalacja (tryb developerski)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```


## 2a) Gdzie uruchamiać (ważne na Windows)

Nie uruchamiaj projektu z `C:\Windows\System32`.

Użyj katalogu roboczego: `C:\Users\MASTER\Desktop\Do pana paczesnego\2026`.
Przykład:

```bat
cd /d "C:\Users\MASTER\Desktop\Do pana paczesnego\2026"
mkdir WERHE_PDFy_tool
cd WERHE_PDFy_tool
```

Dla tej lokalizacji możesz też od razu ustawić `output_root` w `config.json` na:

```text
C:\Users\MASTER\Desktop\Do pana paczesnego\2026\WERHE_PDFy
```

## 3) Konfiguracja

1. Skopiuj `config.example.json` do `config.json`.
2. Uzupełnij `apilo_token`.
3. Jeśli w Twoim koncie Apilo endpointy są inne niż domyślne, popraw:
   - `apilo_orders_endpoint`
   - `apilo_order_details_endpoint`

> Uwaga: struktura API może się różnić między integracjami. W razie potrzeby dopasuj mapowanie pól w `app/apilo_client.py`.

## 4) Uruchomienie

```bash
python main.py
```

W GUI:
1. Wklej token i kliknij **Zapisz token**.
2. Wybierz zakres dat `YYYY-MM-DD`.
3. (Opcjonalnie) wpisz numery zamówień:
   - **Numery Apilo** (`order_number`/`order_id`) rozdzielone przecinkami,
   - **Numery Amazon** rozdzielone przecinkami.
4. Kliknij **Generuj PDF-y** albo **Test na 5 zamówieniach**.

## 5) Wyniki

Pliki pojawią się w katalogu:

```text
<output_root>/PDFy_YYYY_MM/
np. C:\Users\MASTER\Desktop\Do pana paczesnego\2026\WERHE_PDFy\PDFy_YYYY_MM/
```

Struktura:
- `_screenshots/` – screenshoty trackingu,
- `zamowienia/` – pojedyncze PDF-y zamówień,
- `podsumowanie.pdf` – zestawienie zbiorcze,
- `podsumowanie.xlsx` – tabela pomocnicza.

## 6) Logi i błędy

- Log aplikacji: `logs/app.log`
- Aplikacja przetwarza zamówienia niezależnie – błąd jednego zamówienia nie przerywa całego procesu.
- Jeśli tracking nie zawiera rozpoznawalnego statusu doręczenia, aplikacja robi fallback do full-page screenshotu.

## 7) Build .exe

Użyj `build_exe.bat` (szczegóły niżej) lub ręcznie:

```bash
pyinstaller --noconfirm --onefile --windowed --name WerhePdfTool main.py
```

Po buildzie plik `.exe` będzie w `dist/`.

## 8) Różnice FBA/FBC vs magazyn własny

- Zamówienia są rozdzielane po polu `warehouse_type` (`fba` vs inne).
- W podsumowaniu PDF tworzone są osobne sekcje.

## 9) Ważne uwagi biznesowe

- IE599/CC599 pozostaje ręczne (zgodnie z wymaganiami).
- Urząd wymaga dokumentów papierowych – aplikacja optymalizuje przygotowanie materiału do druku.
