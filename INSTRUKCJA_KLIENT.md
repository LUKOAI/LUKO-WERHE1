# Amazon VAT → Arkusz — instrukcja dla osoby w biurze (Windows)

Program łączy raport VAT z Amazon (plik CSV) z fakturami Amazon (pliki PDF) i tworzy arkusz
Excel oraz — jeśli skonfigurowano — wpisuje wynik do arkusza Google. Nie trzeba niczego
instalować: wystarczy jeden plik `AmazonVAT.exe`.

## 1. Jednorazowe przygotowanie (ok. 10 minut)

1. Otrzymany plik `AmazonVAT.exe` zapisz np. w `C:\AmazonVAT\AmazonVAT.exe`.
2. Utwórz foldery:
   * `C:\AmazonVAT\raporty` — tu będą trafiać raporty CSV,
   * `C:\AmazonVAT\faktury` — tu będą trafiać faktury PDF,
   * `C:\AmazonVAT\wyniki` — tu program zapisuje gotowe arkusze.
3. Jeśli wynik ma trafiać do arkusza Google: zapisz otrzymany plik klucza
   `service_account.json` w `C:\AmazonVAT\` (nie wysyłaj go nikomu dalej — to jest hasło do arkusza).
4. Przy pierwszym uruchomieniu Windows może pokazać ostrzeżenie „System Windows ochronił ten
   komputer” (program nie ma podpisu cyfrowego). Kliknij **Więcej informacji → Uruchom mimo to**.

## 2. Co pobrać z Amazon Seller Central (co miesiąc)

1. **Raport**: Seller Central → *Reports* → *Tax Document Library* → zakładka
   *Amazon VAT Transactions Report* → wybierz miesiąc → *Download*. Zapisz plik CSV
   do `C:\AmazonVAT\raporty`.
2. **Faktury**: w *Tax Document Library* pobierz faktury i noty kredytowe za ten sam miesiąc
   (pliki PDF nazwane numerem faktury, np. `PL600IIBG6O6HU.pdf`) do `C:\AmazonVAT\faktury`.
   Jeśli pobierasz je pojedynczo, wystarczy wrzucić wszystkie do tego folderu — program sam je
   dopasuje po numerze faktury. Faktury z poprzednich miesięcy mogą tam zostać.

## 3. Uruchomienie (2 minuty)

1. Uruchom `AmazonVAT.exe`.
2. **Raport CSV** → *Wybierz…* → zaznacz plik(i) raportu z `C:\AmazonVAT\raporty`.
3. **Folder z fakturami PDF** → *Wybierz…* → `C:\AmazonVAT\faktury`.
4. **Folder na wyniki** → `C:\AmazonVAT\wyniki`.
5. Jeśli wynik ma iść do Google: wpisz **ID arkusza Google** (fragment adresu arkusza między
   `/d/` a `/edit`) i wskaż **Klucz konta serwisowego** (`C:\AmazonVAT\service_account.json`).
   Program zapamięta te ustawienia.
6. Kliknij **Uruchom**. W oknie pojawi się dziennik, a na końcu podsumowanie, np.
   `transakcje: 44 | PDF: 44 | dopasowane: 44 | bez PDF: 0`.
7. Kliknij **Otwórz wynik** (plik Excel) albo otwórz arkusz Google — zakładki zostały nadpisane.

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
