# LUKO AmaFakt — instrukcja dla osoby w biurze (Windows)

LUKO AmaFakt łączy raport VAT z Amazon (plik CSV) z fakturami Amazon (pliki PDF) i tworzy arkusz
Excel oraz — jeśli skonfigurowano — wpisuje wynik do arkusza Google. Nie trzeba niczego
instalować: wystarczy jeden plik `LUKO-AmaFakt.exe`.

## 1. Jednorazowe przygotowanie (ok. 10 minut)

1. Otrzymany plik `LUKO-AmaFakt.exe` zapisz np. w `C:\LUKO-AmaFakt\LUKO-AmaFakt.exe`.
2. Utwórz foldery:
   * `C:\LUKO-AmaFakt\raporty` — tu będą trafiać raporty CSV,
   * `C:\LUKO-AmaFakt\faktury` — tu będą trafiać faktury PDF,
   * `C:\LUKO-AmaFakt\wyniki` — tu program zapisuje gotowe arkusze.
3. Jeśli wynik ma trafiać do arkusza Google: zapisz otrzymany plik klucza
   `service_account.json` w `C:\LUKO-AmaFakt\` (nie wysyłaj go nikomu dalej — to jest hasło do arkusza).
4. Przy pierwszym uruchomieniu Windows może pokazać ostrzeżenie „System Windows ochronił ten
   komputer” (program nie ma podpisu cyfrowego). Kliknij **Więcej informacji → Uruchom mimo to**.

## 1a. Połączenie z arkuszem Google (robi właściciel arkusza, jednorazowo, ok. 15 minut)

Program może wpisywać wyniki prosto do Waszego arkusza Google. Do tego potrzebne jest
„konto techniczne” (konto serwisowe) założone na **Waszym** koncie Google — dzięki temu klucz,
dane i arkusz pozostają wyłącznie w firmie. Robi to osoba zalogowana na konto Google, do
którego należy arkusz. Bez tego kroku program działa tak samo, tylko wynik importuje się do
Google ręcznie (patrz punkt 3, krok 8).

1. Wejdź na https://console.cloud.google.com (to samo konto Google, co arkusz). Przy
   pierwszym wejściu zaakceptuj regulamin; karta płatnicza nie jest potrzebna.
2. U góry po lewej kliknij listę projektów → **Nowy projekt** → nazwa `LUKO-AmaFakt` → **Utwórz**
   → **Wybierz projekt**.
3. W wyszukiwarce u góry wpisz `Google Sheets API` → otwórz → **Włącz**. Powtórz dla
   `Google Drive API`.
4. Menu ☰ → **IAM i administracja** → **Konta serwisowe** → **Utwórz konto serwisowe**.
   Nazwa `luko-amafakt` → **Utwórz i kontynuuj** → rolę pomiń (**Dalej**, **Gotowe**).
5. Kliknij utworzone konto → zakładka **Klucze** → **Dodaj klucz** → **Utwórz nowy klucz**
   → **JSON** → **Utwórz**. Pobierze się plik `.json` — zapisz go jako
   `C:\LUKO-AmaFakt\service_account.json`. To jest hasło do arkusza: nie wysyłaj go e-mailem
   poza firmę, nie wrzucaj do chmury.
6. Otwórz ten plik w Notatniku i skopiuj wartość pola `client_email`
   (wygląda jak `luko-amafakt@luko-amafakt-123456.iam.gserviceaccount.com`).
7. Otwórz arkusz Google, do którego mają trafiać wyniki → **Udostępnij** → wklej ten adres
   → rola **Edytor** → odznacz „Powiadom” → **Wyślij**.
8. ID arkusza to fragment adresu strony między `/d/` a `/edit`
   (np. `1LbgN5wfsZG_zPuU25JZ6w7gP2jjrfF9WLRJBemJYm9I`). Zapisz go — wpiszesz go w programie.

## 2. Co pobrać z Amazon Seller Central (co miesiąc)

1. **Raport**: Seller Central → *Reports* → *Tax Document Library* → zakładka
   *Amazon VAT Transactions Report* → wybierz miesiąc → *Download*. Zapisz plik CSV
   do `C:\LUKO-AmaFakt\raporty`.
2. **Faktury**: w *Tax Document Library* pobierz faktury i noty kredytowe za ten sam miesiąc
   (pliki PDF nazwane numerem faktury, np. `PL600IIBG6O6HU.pdf`) do `C:\LUKO-AmaFakt\faktury`.
   Jeśli pobierasz je pojedynczo, wystarczy wrzucić wszystkie do tego folderu — program sam je
   dopasuje po numerze faktury. Faktury z poprzednich miesięcy mogą tam zostać.

## 3. Uruchomienie (2 minuty)

1. Uruchom `LUKO-AmaFakt.exe`.
2. **Raport CSV** → *Wybierz…* → zaznacz plik(i) raportu z `C:\LUKO-AmaFakt\raporty`.
3. **Folder z fakturami PDF** → *Wybierz…* → `C:\LUKO-AmaFakt\faktury`.
4. **Folder na wyniki** → `C:\LUKO-AmaFakt\wyniki`.
5. Jeśli wynik ma iść do Google: wpisz **ID arkusza Google** (fragment adresu arkusza między
   `/d/` a `/edit`) i wskaż **Klucz konta serwisowego** (`C:\LUKO-AmaFakt\service_account.json`).
   Program zapamięta te ustawienia.
6. Kliknij **Uruchom**. W oknie pojawi się dziennik, a na końcu podsumowanie, np.
   `transakcje: 44 | PDF: 44 | dopasowane: 44 | bez PDF: 0`.
7. Kliknij **Otwórz wynik** (plik Excel) albo otwórz arkusz Google — zakładki zostały nadpisane.
8. Bez połączenia z Google (punkt 1a pominięty): w Google Sheets **Plik → Importuj → Prześlij**
   → wybierz plik Excel z folderu wyników → „Zastąp arkusz kalkulacyjny” lub „Wstaw nowe
   arkusze”. Wszystkie zakładki wchodzą 1:1.

## 4. Co sprawdzić po uruchomieniu

* Zakładka **Diagnostyka** — lista rzeczy do wyjaśnienia: transakcje bez faktury PDF (trzeba
  ją dograć do folderu i uruchomić ponownie), różnice kwot między fakturą a raportem, noty
  kredytowe do faktur z poprzedniego miesiąca, brak kursu waluty.
* Jeśli w dzienniku jest **„API NBP niedostępne”** — komputer nie ma połączenia z internetem
  albo firewall blokuje `api.nbp.pl`; kolumny w PLN będą puste. Po przywróceniu połączenia
  wystarczy uruchomić ponownie.

## 5. Co zrobić, gdy coś nie działa

Wyślij do opiekuna narzędzia: treść dziennika z okna programu (zaznacz → Ctrl+C) oraz plik
`faktury.json` z folderu wyników (zawiera to, co program odczytał z PDF-ów). Nie trzeba
wysyłać faktur.
