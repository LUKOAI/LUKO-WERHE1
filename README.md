# LUKO-WERHE1

Repozytorium narzędzi dla klienta WERHE / WERKON.

## 1. LUKO AmaFakt (`amazon_vat_merger/`)

Łączy raport **Amazon VAT Transactions Report** (CSV z Seller Central) z **fakturami VCS w PDF**
(te same, które Amazon generuje pod „Invoice Url") i buduje jeden arkusz ze wszystkimi danymi:

* zakładka **Wszystko** – każda transakcja z CSV + dane z PDF (nazwisko/nazwa kupującego, ulica,
  miasto i kod, NIP, opis produktu, kwota faktury, kontrola zgodności kwot PDF/CSV);
* zakładki **per kraj i schemat**, osobno sprzedaż i korekty (np. `DE OSS` i `DE OSS KOREKTA` –
  zwroty i noty kredytowe z kwotami ujemnymi; `FR Lokalna`, `CZ WDT`, `FR Marketplace`): wiersz 1
  (kraj, schemat), wiersz 2 nagłówki, wiersz 3 pusty i pierwsze kolumny **dokładnie jak w arkuszu
  próbnym klienta** (układ EUR: netto PLN, netto EUR, stawka, „Kwota należnego Vat'u”; układ walut
  obcych: netto PLN, netto EUR, VAT EUR, netto/VAT w walucie, stawka); dalej, na szarym tle,
  kolumny dodatkowe narzędzia (VAT PLN, typ transakcji, ASIN, SKU, nazwa produktu, kurs…);
  na końcu wiersz `RAZEM` (formuły SUM);
* zakładka **Diagnostyka** – brakujące PDF-y, PDF-y bez transakcji, różnice kwot, ostrzeżenia parsera,
  brak kursu PLN.

Wynik zapisywany jest do `.xlsx` i opcjonalnie wypychany do **Google Sheets**.

### Szybki start (demo)

1. Sklonuj repo i przełącz się na gałąź z narzędziem:
   `git clone https://github.com/LUKOAI/LUKO-WERHE1.git && cd LUKO-WERHE1 && git checkout claude/amazon-reports-merger-0mpcvu`
2. Wrzuć dane wejściowe:
   * `dane/` – raport(y) CSV **Amazon VAT Transactions Report** (Seller Central → Reports →
     Tax Document Library → Amazon VAT Transactions Report → Download),
   * `dane/faktury/` – faktury i noty kredytowe PDF (Tax Document Library / linki z kolumny
     „Invoice Url" raportu),
   * opcjonalnie `dane/kursy.csv` – własne kursy PLN (`waluta;data;kurs`).
3. Uruchom:
   * Windows bez Pythona: `LUKO-AmaFakt.exe` (okienko; plik z GitHub Actions → *Artifacts* →
     `LUKO-AmaFakt-windows`), instrukcja dla biura: `INSTRUKCJA_KLIENT.md`
   * macOS / Linux: `./demo.sh`
   * Windows z Pythonem: `demo.bat`
   * okienko z Pythona: `python -m amazon_vat_merger.gui`

   Skrypt sam tworzy `.venv`, instaluje `requirements-merger.txt`, zapisuje
   `output/amazon_vat_<data>.xlsx` i otwiera plik. Kursy PLN pobiera z API NBP
   (tabela A, ostatnia przed datą bazową).
4. Do Google Sheets:
   * ręcznie: Google Sheets → **Plik → Importuj → Prześlij** plik xlsx (wszystkie zakładki),
   * automatycznie: `./demo.sh <ID_ARKUSZA>` (Windows: `demo.bat <ID_ARKUSZA>`) z kluczem
     konta serwisowego w `credentials/service_account.json` – zakładki w arkuszu są nadpisywane
     w miejscu, inne zakładki zostają. ID arkusza to fragment URL między `/d/` a `/edit`.

### Instalacja ręczna

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-merger.txt
python -m amazon_vat_merger --csv raport.csv --pdf faktury/ --out output/wynik.xlsx
```

### Scenariusz demonstracji dla klienta (ok. 5 minut)

1. Pokaż wejście: katalog `dane/` z raportem CSV z Seller Central i katalogiem faktur PDF
   (różne rynki: DE/FR/IT/ES/NL/UK, faktury, noty kredytowe, B2B).
2. Uruchom `./demo.sh <ID_ARKUSZA>` (albo `demo.bat …`) – w terminalu widać: liczbę transakcji,
   liczbę PDF, ile dopasowano, listę zakładek.
3. Odśwież arkusz Google: zakładka **Wszystko** (nazwisko i adres kupującego z PDF obok danych
   z raportu, kwoty netto/VAT/brutto, EUR, PLN z kursem i datą kursu, opis produktu, kontrola
   „Zgodność kwoty PDF/CSV").
4. Pokaż zakładki per kraj/schemat (np. `DE OSS`, `FR Lokalna`, `CZ WDT`) – układ jak w arkuszu
   próbnym, wiersz RAZEM.
5. Pokaż **Diagnostykę**: co program sam wyłapał (brakujące PDF-y, noty do faktur z poprzedniego
   okresu, rozbieżny numer zamówienia, brak kursu dla GBP).
6. Pokaż notę kredytową (np. `DE60006WG6O6HC`): typ dokumentu, faktura pierwotna, kwoty ujemne,
   uwaga do kursu.

Opcje:

| opcja | znaczenie |
|---|---|
| `--csv PLIK` | raport CSV (można podać kilka razy – np. kilka miesięcy) |
| `--pdf PLIK\|KATALOG` | faktura PDF lub katalog z fakturami (rekurencyjnie), można podać kilka razy |
| `--out PLIK.xlsx` | plik wynikowy (domyślnie `output/amazon_vat.xlsx`) |
| `--json PLIK.json` | zrzut wszystkich pól odczytanych z PDF (do diagnostyki nowych układów faktur) |
| `--sheet-id ID\|URL` | arkusz Google do nadpisania (zakładki o tych samych nazwach są czyszczone i zapisywane od nowa) |
| `--credentials klucz.json` | klucz konta serwisowego Google |
| `--rates-file kursy.csv` | własne kursy PLN (`waluta;data;kurs`), patrz `examples/kursy_przyklad.csv` |
| `--no-nbp` | nie pobieraj kursów z API NBP |
| `--rate-basis invoice\|shipment\|order` | data bazowa kursu (domyślnie data faktury z PDF) |

### Co sprawdza Diagnostyka

* brakujące PDF-y i PDF-y bez wiersza w CSV, zduplikowane pliki, niejednoznaczne dopasowania
  po numerze zamówienia (PDF bez czytelnego numeru faktury);
* kwota faktury / VAT z PDF ≠ CSV (dla faktur wielopozycyjnych – suma pozycji), waluta PDF ≠ CSV,
  numer zamówienia PDF ≠ CSV, typ dokumentu (nota kredytowa) ≠ typ transakcji (zwrot);
* noty kredytowe do faktur spoza raportu (faktura pierwotna z wcześniejszego okresu) – kurs PLN
  liczony wtedy z daty noty, co jest opisane w kolumnie `Uwaga do kursu`;
* brak kursu PLN, pominięte duplikaty wierszy CSV.

### Łączenie danych

* Klucz łączenia: kolumna CSV **VAT Invoice Number** = numer faktury z PDF (etykieta „Nr faktury” /
  „Numero ricevuta” / „Numéro de la facture” / …, potem nazwa pliku, potem numer w treści).
  Gdy numeru nie da się odczytać, używany jest numer zamówienia (tylko gdy jest jednoznaczny).
* Faktura wielopozycyjna → kilka wierszy CSV z tym samym numerem; opis produktu dopasowywany po ASIN.
* Kwoty (netto/VAT/brutto) liczone z CSV: towar + wysyłka + opakowanie, z uwzględnieniem promocji
  (`… Promo Amount`). Zwroty (REFUND/RETURN) mają kwoty ujemne.

### Reguły zakładek

| kategoria | warunek (kolumny CSV) | kraj w nazwie zakładki |
|---|---|---|
| `OSS` | `Tax Reporting Scheme` = `VCS_EU_OSS` | kraj dostawy (`Ship To Country`) |
| `Marketplace` | `Tax Collection Responsibility` = `Marketplace` (Amazon deemed reseller, np. UK) | kraj rejestracji sprzedawcy |
| `Eksport` | `Export Outside EU` = true | kraj rejestracji sprzedawcy |
| `WDT` | nabywca z NIP UE, stawka 0 %, inny kraj wysyłki i dostawy | kraj rejestracji sprzedawcy |
| `B2B` | nabywca z NIP, VAT naliczony | kraj rejestracji sprzedawcy |
| `Lokalna` | pozostałe | kraj rejestracji sprzedawcy |

Reguła jest w jednym miejscu (`report.py: classify()` i `tab_country()`) – łatwo ją zmienić.

### Kursy walut – skąd i z jakiego dnia

* **Źródło**: Narodowy Bank Polski, tabela A kursów średnich, pobierana z oficjalnego API
  `https://api.nbp.pl/api/exchangerates/rates/a/<waluta>/<od>/<do>/` (bez klucza, bez opłat).
  Numer tabeli NBP (np. `166/A/NBP/2026`) jest zapisywany w kolumnie `Źródło kursu`,
  a data jej publikacji w `Data kursu`.
* **Dzień kursu** (art. 31a ust. 1–2 ustawy o VAT): ostatnia tabela opublikowana **przed** dniem
  powstania obowiązku podatkowego; jeśli fakturę wystawiono wcześniej – przed dniem wystawienia
  faktury. Narzędzie przyjmuje jako dzień bazowy **wcześniejszą** z dat: data faktury (z PDF)
  i data wysyłki (`Shipment Date` z raportu). Dzień bazowy jest w kolumnie `Data bazowa kursu`.
  Przykład: wysyłka i faktura 29.08 (sobota) → kurs z tabeli z piątku 28.08.
* **Noty kredytowe / zwroty** (art. 31b ust. 1): kurs faktury pierwotnej, jeśli ta faktura jest
  w przetwarzanych danych; w przeciwnym razie kurs z dnia noty i wpis „kurs z daty noty” w kolumnie
  `Uwaga do kursu` oraz w `Diagnostyce`.
* **Zaokrąglanie**: netto i VAT przeliczane osobno i zaokrąglane do grosza (HALF_UP),
  brutto = netto + VAT.
* **Gdy NBP jest niedostępne**: 1) plik `--rates-file` (`waluta;data;kurs`, data = data
  publikacji tabeli), 2) kurs Amazon z raportu (`Invoice Level Exchange Rate`, tylko faktury
  B2B wystawione w PLN) – wtedy `Źródło kursu` = „Amazon (CSV)”. Bez żadnego źródła kolumny PLN
  są puste, a `Diagnostyka` wylicza takie wiersze. Nigdy nie jest używany kurs „z głowy”.
* Kwoty **EUR** dla rynków w EUR pochodzą wprost z raportu; dla walut obcych (SEK, GBP) tylko
  wtedy, gdy Amazon podał przeliczenie na fakturze/w raporcie (OSS rozlicza się w EUR po kursie
  EBC z ostatniego dnia kwartału – tego narzędzie nie liczy).
* Domyślny dzień bazowy można zmienić: `--rate-basis shipment` (tylko data wysyłki) lub `order`.

### Google Sheets (system klienta)

Konto serwisowe zakłada **właściciel arkusza (konto Google klienta)** – wtedy klucz, dane i arkusz
pozostają w firmie klienta; opiekun narzędzia nie ma dostępu do danych (kroki dla biura:
`INSTRUKCJA_KLIENT.md`, punkt 1a).

1. Google Cloud → projekt → włącz **Google Sheets API** i **Google Drive API**.
2. Utwórz konto serwisowe, pobierz klucz JSON (nie wrzucać do repo – `.gitignore` już to blokuje).
3. Udostępnij docelowy arkusz adresowi e-mail konta serwisowego (Edytor).
4. `python -m amazon_vat_merger --csv … --pdf … --sheet-id <ID z URL> --credentials klucz.json`

Każde uruchomienie nadpisuje zakładki o tych samych nazwach (wartości i formaty), inne zakładki
zostają. Wartości idą w trybie RAW: tekst jest tekstem bez żadnego prefiksu (kody pocztowe `01234`,
numery zamówień i SKU nie zamieniają się w liczby), daty jako numery seryjne z formatem daty,
kwoty jako liczby z formatem `#,##0.00`, stawki VAT `0.0%` (5,5 % nie zaokrągla się do 6 %).
Formuły RAZEM idą osobnym `batch_update` – jego błąd jest zgłaszany jako błąd zapisu
(`GoogleSheetsError`); formatowanie idzie drugim, niekrytycznym `batch_update` (tylko ostrzeżenie).
Klient ma backoff na limit 60 zapisów/min.

Zakładki własnego wzoru (`DE OSS`, `FR Lokalna KOREKTA` …; kod kraju + kategoria, ewentualnie KOREKTA), które istnieją w arkuszu, a nie
zostały zapisane w tym uruchomieniu, są czyszczone i dostają notatkę „Brak transakcji tego typu
w ostatnim uruchomieniu …” – korekty pojawiają się nieregularnie i stara zakładka nie może
udawać aktualnej. Zakładki o innych nazwach nie są ruszane.

Błąd po stronie Google (arkusz nieudostępniony kontu serwisowemu, złe ID, wyłączone API, brak
sieci) nie przerywa pracy: plik `.xlsx` jest już zapisany, `JobResult.push_error` niesie polski
komunikat z ID arkusza i adresem konta serwisowego, CLI kończy się kodem 3, okienko pokazuje
status „Zakończono – błąd Google Sheets”.

Bez konta serwisowego: otwórz Google Sheets → **Plik → Importuj → Prześlij** plik `.xlsx` –
wszystkie zakładki, formuły `RAZEM` i formaty wchodzą 1:1 (linki z kolumny „Zakładka” są w postaci
Excela `#'DE OSS'!A5` i po imporcie mogą nie działać – działają przy zapisie przez konto serwisowe).

### Linki „Wszystko” → zakładka

Kolumna A („Zakładka”) w `Wszystko` to `Link(tab, row)` (podklasa `Formula`): w xlsx
`=HYPERLINK("#'DE OSS'!A5","DE OSS")`, w Google Sheets `=HYPERLINK("#gid=<sheetId>&range=A5","DE OSS")`
– `gid` jest znany dopiero po utworzeniu zakładek, dlatego formuły idą po zapisaniu wszystkich
wartości; kolejne wiersze tej samej kolumny jadą jednym `updateCells`. Numer wiersza (`MergedRow.tab_row`)
nadaje `build_group_sheets`, więc `build_sheets` buduje zakładki krajów przed `Wszystko`.

### Autor, wersja, kontakt

`amazon_vat_merger/__init__.py`: `AUTHOR`, `SUPPORT_EMAIL` (support@netanaliza.com), `COPYRIGHT_YEAR`,
`about_line()`. Widoczne: stopka okna (adres klikalny), pierwszy wiersz zakładki `Diagnostyka`
(plus wiersz „Program” i „Wygenerowano”), `--version`/`--help` w CLI, właściwości plików `.exe`
(`tools/make_version_info.py` generuje plik `--version-file` dla PyInstallera w GitHub Actions).

### Testy

```bash
python -m pytest -q
```

Testy na prawdziwych próbkach (`samples/`, katalog ignorowany przez git – dane osobowe) są pomijane,
gdy próbek nie ma.

### Obsługiwane języki faktur

Etykiety: PL, IT, FR, DE, ES, NL, SV, EN (`labels.py`). Parser opiera się na stałym układzie faktury
Amazon (współrzędne słów), więc nowe języki wymagają zwykle tylko dopisania etykiet. Nieznane pola
nie przerywają przetwarzania – trafiają jako ostrzeżenia do `Diagnostyka` i kolumny `Ostrzeżenia PDF`.

### Jak to działa – narzędzia, koszty, przepływ danych

**Składniki**

| element | co to jest | koszt |
|---|---|---|
| `LUKO-AmaFakt.exe` / `python -m amazon_vat_merger` | program w Pythonie (biblioteki open source: pdfplumber – odczyt PDF, openpyxl – Excel, gspread – Google Sheets, requests – NBP) uruchamiany **lokalnie na komputerze klienta** | 0 zł |
| API NBP | publiczne API kursów walut | 0 zł, bez klucza |
| Google Sheets API + konto serwisowe | projekt w Google Cloud, konto techniczne z własnym e-mailem, któremu udostępnia się arkusz | 0 zł (limit 60 zapisów/min – narzędzie się w nim mieści) |
| GitHub (repozytorium prywatne + Actions) | kod i automatyczna budowa `.exe` przy każdej zmianie | 0 zł w limicie darmowym (2000 min/mies.) |
| Excel / Google Sheets | podgląd wyników | już posiadane |

Nie ma żadnego modelu AI, serwera pośredniczącego ani abonamentu. Koszt jednego uruchomienia = 0 zł.

**Przepływ danych**

1. Osoba w biurze pobiera z Seller Central raport CSV i faktury PDF na swój komputer.
2. Program czyta je lokalnie; jedyne połączenia wychodzące to `api.nbp.pl` (pytanie o kurs:
   waluta + zakres dat, bez danych klienta) oraz – opcjonalnie – `sheets.googleapis.com`
   (zapis zakładek do wskazanego arkusza, uwierzytelnienie kluczem konta serwisowego).
3. Wynik: plik `.xlsx` w folderze wyników i/lub zakładki w arkuszu Google klienta.
   Dane osobowe kupujących pozostają u klienta (jego komputer, jego arkusz Google).
4. W repozytorium nie ma żadnych danych klienta (raporty, faktury, klucze są ignorowane przez git).

**Utrzymanie**: zmiana w kodzie → push do GitHuba → Actions buduje nowe `LUKO-AmaFakt.exe`
(zakładka *Actions* → ostatni przebieg → *Artifacts* → `LUKO-AmaFakt-windows`) → plik wysyła się
do biura i podmienia stary.

### Dostarczanie nowych plików – warianty

1. **Lokalnie u klienta (zalecane na start)** – osoba w biurze pobiera raport i faktury z Seller
   Central, uruchamia `LUKO-AmaFakt.exe`, wynik trafia do ich arkusza Google. Zero przesyłania danych
   osobowych poza firmę. Instrukcja: `INSTRUKCJA_KLIENT.md`.
2. **Wspólny folder (Google Drive / OneDrive)** – klient wrzuca raport i faktury do folderu
   udostępnionego opiekunowi narzędzia, który uruchamia program u siebie. Wymaga zgody klienta
   na przetwarzanie danych kupujących poza firmą (umowa powierzenia).
3. **Automatycznie z Amazon (etap 2)** – Amazon Selling Partner API: raport
   `GET_VAT_TRANSACTION_DATA` i pobieranie faktur bez ręcznego klikania; wymaga rejestracji
   aplikacji deweloperskiej w Seller Central klienta i tokenu odświeżania. Do zrobienia po
   zaakceptowaniu prototypu.

Ręczne pobieranie faktur można też ominąć częściowo: raport zawiera kolumnę `Invoice Url`
(link do PDF w Seller Central) – narzędzie ją pokazuje w zakładce `Wszystko`, ale pobranie
wymaga zalogowanej sesji Seller Central, więc dziś robi to człowiek.

## 2. WERHE/WERKON DEMO (`main.py`)

Wersja demonstracyjna GUI (bez API Apilo): generuje przykładowy PDF.

```bash
pip install -r requirements.txt
python main.py
```
