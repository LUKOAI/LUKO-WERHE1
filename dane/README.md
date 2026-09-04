# dane/ – wejście do demo (katalog ignorowany przez git)

* `dane/*.csv` – raport **Amazon VAT Transactions Report** (Seller Central → Reports → Tax Document
  Library → Amazon VAT Transactions Report → Download). Można wrzucić kilka plików (kilka miesięcy).
* `dane/faktury/` – faktury i noty kredytowe PDF (z Tax Document Library albo pobrane linkami
  z kolumny „Invoice Url" raportu). Nazwa pliku = numer faktury (np. `PL600IIBG6O6HU.pdf`),
  ale parser czyta numer także z treści.
* `dane/kursy.csv` (opcjonalnie) – własne kursy PLN `waluta;data;kurs`, gdy nie ma dostępu do NBP.
