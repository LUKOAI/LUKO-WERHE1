# LUKO-WERHE1

Repozytorium narzędzi dla klienta WERHE / WERKON.

## 1. Amazon VAT merger (`amazon_vat_merger/`)

Łączy raport **Amazon VAT Transactions Report** (CSV z Seller Central) z **fakturami VCS w PDF**
(te same, które Amazon generuje pod „Invoice Url") i buduje jeden arkusz ze wszystkimi danymi:

* zakładka **Wszystko** – każda transakcja z CSV + dane z PDF (nazwisko/nazwa kupującego, ulica,
  miasto i kod, NIP, opis produktu, kwota faktury, kontrola zgodności kwot PDF/CSV);
* zakładki **per kraj i schemat** (np. `DE OSS`, `FR Lokalna`, `CZ WDT`, `FR Marketplace`) w układzie
  zgodnym z arkuszem próbnym klienta, z wierszem `RAZEM` (formuły SUM);
* zakładka **Diagnostyka** – brakujące PDF-y, PDF-y bez transakcji, różnice kwot, ostrzeżenia parsera,
  brak kursu PLN.

Wynik zapisywany jest do `.xlsx` i opcjonalnie wypychany do **Google Sheets**.

### Instalacja

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### Uruchomienie

```bash
python -m amazon_vat_merger --csv raport.csv --pdf faktury/ --out output/wynik.xlsx
```

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

### Kursy PLN

Kolejność źródeł: plik `--rates-file` → API NBP (tabela A, ostatni kurs opublikowany **przed** datą
bazową – art. 31a ustawy o VAT) → kurs Amazon z CSV (`Invoice Level Exchange Rate`, tylko gdy
waluta faktury = PLN). Źródło i data kursu są w kolumnach `Źródło kursu` / `Data kursu`.
Bez dostępu do NBP i bez pliku kursów kolumny PLN pozostają puste, a `Diagnostyka` to raportuje.

### Google Sheets (system klienta)

1. Google Cloud → projekt → włącz **Google Sheets API** i **Google Drive API**.
2. Utwórz konto serwisowe, pobierz klucz JSON (nie wrzucać do repo – `.gitignore` już to blokuje).
3. Udostępnij docelowy arkusz adresowi e-mail konta serwisowego (Edytor).
4. `python -m amazon_vat_merger --csv … --pdf … --sheet-id <ID z URL> --credentials klucz.json`

Każde uruchomienie nadpisuje zakładki o tych samych nazwach (wartości i formaty), inne zakładki
zostają. Tekst trafia do komórek jako tekst (kody pocztowe `01234`, numery zamówień i SKU nie
zamieniają się w liczby), daty jako daty, kwoty jako liczby z formatem `#,##0.00`. Formatowanie
idzie jednym `batch_update`, klient ma backoff na limit 60 zapisów/min.

Bez konta serwisowego: otwórz Google Sheets → **Plik → Importuj → Prześlij** plik `.xlsx` –
wszystkie zakładki, formuły `RAZEM` i formaty wchodzą 1:1.

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

## 2. WERHE/WERKON DEMO (`main.py`)

Wersja demonstracyjna GUI (bez API Apilo): generuje przykładowy PDF.

```bash
pip install -r requirements.txt
python main.py
```
