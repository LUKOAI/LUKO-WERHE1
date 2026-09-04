# Auto_Potwierdzenia — instrukcja instalacji i obsługi

Program automatycznie przygotowuje comiesięczną dokumentację dla urzędu skarbowego
dla zamówień eksportowych poza UE: pobiera zamówienia z Apilo, robi zrzuty ekranu
(tracking kuriera, Amazon, panel Apilo), ściąga faktury (Apilo i Amazon)
i skleja wszystko w gotowe do druku pliki PDF.

---

## CZĘŚĆ 1 — INSTALACJA (jednorazowo, na nowym komputerze)

### 1.1. Zainstaluj Pythona

1. Wejdź na https://www.python.org/downloads/ i pobierz **Python 3.11** lub nowszy.
2. Uruchom instalator. **WAŻNE:** na pierwszym ekranie zaznacz kratkę
   **„Add Python to PATH"** — bez tego nic nie będzie działać.
3. Kliknij „Install Now" i poczekaj do końca.

### 1.2. Pobierz program

1. Wejdź na stronę projektu na GitHub i pobierz ZIP gałęzi
   `claude/desktop-automation-tool-PhjMR` (przycisk **Code → Download ZIP**).
2. Rozpakuj ZIP do docelowego folderu, np.:
   `C:\Users\MASTER\Desktop\Do pana paczesnego\2026\WERHE_PDFy_tool\app\`

Wszystkie komendy poniżej wpisuje się w **PowerShell** (menu Start → wpisz
„PowerShell" → Enter), zawsze zaczynając od wejścia do folderu programu:

```powershell
cd "C:\Users\MASTER\Desktop\Do pana paczesnego\2026\WERHE_PDFy_tool\app\LUKO-WERHE1-claude-desktop-automation-tool-PhjMR"
```

### 1.3. Zainstaluj biblioteki

Wklej po kolei (każdą linię osobno, czekaj aż skończy):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install firefox
```

Trwa to kilka minut. Program używa przeglądarki **Firefox** (instaluje się
automatycznie powyższą komendą — to osobna kopia, nie rusza Twojego Firefoksa).

### 1.4. Utwórz plik konfiguracyjny

```powershell
copy config.example.json config.json
```

Otwórz `config.json` w Notatniku i uzupełnij:

| Pole | Co wpisać |
|---|---|
| `apilo_base_url` | adres Twojego konta Apilo, np. `https://werhe.apilo.com` |
| `apilo_client_id` | Client ID z panelu Apilo (patrz 1.5) |
| `apilo_client_secret` | Client Secret z panelu Apilo |
| `apilo_auth_code` | Kod autoryzacji z panelu Apilo (**ważny krótko!** — patrz 1.5) |
| `output_root` | folder, gdzie mają lądować wyniki |
| `apilo_panel_url` | adres panelu Apilo, np. `https://werhe.apilo.com` |

Reszty pól nie ruszaj. **Uwaga na format:** wartości w cudzysłowach, po każdej
linii przecinek (oprócz ostatniej). Jak plik się „zepsuje", skopiuj świeży
z `config.example.json` i uzupełnij od nowa.

### 1.5. Dane API z panelu Apilo

W panelu Apilo: **Ustawienia → API → Aplikacje** (lub podobnie) → utwórz/otwórz
aplikację. Skopiuj **Client ID** i **Client Secret**. Potem wygeneruj
**Kod autoryzacji** — on wygasa po kilku minutach, więc od razu wklej go
do `config.json` i przejdź do kroku 1.6.

### 1.6. Pierwsze uruchomienie i połączenie z Apilo

```powershell
.\.venv\Scripts\pythonw.exe main.py
```

(albo dwuklik na `Auto_Potwierdzenia.bat`)

W oknie programu kliknij **„Połącz z Apilo"**. Powinno pojawić się:
`Autentykacja Apilo OK — token ważny do ...`. Token odświeża się potem sam
(ważny 21 dni, odnawiany automatycznie). Jeśli błąd — najczęściej wygasł kod
autoryzacji: wygeneruj nowy w Apilo, wklej do `config.json`, spróbuj ponownie.

### 1.7. Logowania do Amazon i panelu Apilo (jednorazowo)

W programie są trzy przyciski logowania:

1. **„Zaloguj do Amazon EU"** — otworzy się Firefox; zaloguj się do Seller
   Central (e-mail, hasło, kod 2FA). Po zalogowaniu zamknij okno.
2. **„Zaloguj do Amazon USA"** — to samo dla amerykańskiego panelu
   (potrzebne tylko, jeśli są zamówienia z USA/Kanady/Meksyku).
3. **„Zaloguj do panelu Apilo"** — to samo dla panelu www Apilo.

Sesje zapisują się w folderze `browser_profiles` i **pamiętają logowanie** —
nie trzeba tego robić przy każdym uruchomieniu. Trzeba powtórzyć tylko, gdy
Amazon/Apilo wyloguje (co kilka tygodni). Panel Amazona ustaw na **język
angielski** (program tego wymaga do rozpoznawania przycisków).

---

## CZĘŚĆ 2 — OBSŁUGA (co miesiąc)

### 2.1. Normalny przebieg

1. Uruchom program (`Auto_Potwierdzenia.bat` lub komenda z 1.6).
2. Ustaw **daty od–do** (np. cały miesiąc: 2026-07-01 do 2026-07-31).
3. Zostaw checkboxy tak, jak są (wszystkie ścieżki włączone).
4. Kliknij **„Generuj PDF-y"**.
5. Nie wyłączaj komputera. Będą otwierać się okna przeglądarki — **nie zamykaj
   ich i nie klikaj w nich** (program sam nimi steruje).
6. Jeśli pojawi się komunikat `UWAGA: serwis prosi o logowanie/kod 2FA` —
   wpisz dane/kod w otwartym oknie przeglądarki; program poczeka (do 5 minut)
   i sam pojedzie dalej.
7. Na końcu: `Gotowe. OK: X, błędy: Y` i ścieżka do wyników.

Pełny miesiąc trwa zwykle **1–2 godziny** (program celowo zwalnia zapytania
do Apilo — limit API 150/min — oraz robi przerwy między stronami Amazona).

### 2.2. Wyniki — struktura folderów

```
WERHE_PDFy\PDFy_2026_07\
├── DO_WYDRUKU\          ← TO DRUKUJESZ
│   ├── WA260605861.pdf      (jeden plik = jedno zamówienie:
│   ├── WB260604227.pdf       zrzuty ekranu + wszystkie faktury)
│   ├── ...
│   ├── podsumowanie.pdf
│   └── podsumowanie.xlsx
└── DO_KONTROLI\         ← materiały robocze, NIE drukować
    ├── WA260605861\         (pojedyncze zrzuty, pojedyncze faktury)
    ├── WA260604959\         (materiały zamówień POMINIĘTYCH,
    │                         pliki _DEBUG_*.png i *_INVALID.bin)
    └── ...
```

- **DO_WYDRUKU** — komplet dla urzędu: zaznacz wszystkie pliki → drukuj.
- **DO_KONTROLI** — surowe materiały każdego zamówienia (także pominiętych) —
  do sprawdzenia w razie wątpliwości. Można archiwizować, nie kasować.

### 2.3. Ręczny wybór zamówień (opcjonalnie)

Aby przetworzyć tylko konkretne zamówienia, wpisz ich numery (po przecinku):

- pole **„Numery Apilo"** — np. `WA260605861, WB260604227`
- pole **„Numery Amazon"** — np. `305-3236501-2279526`

Daty ustaw tak, żeby obejmowały te zamówienia. Puste pola = wszystkie
zamówienia z zakresu dat.

### 2.4. Co program robi z każdym typem zamówienia

| Typ | Dowód w PDF |
|---|---|
| Wysyłka własna, **dostarczona** | zrzut trackingu kuriera (UPS/DPD/Poczta) + faktura |
| Wysyłka własna, **niedostarczona** | zrzut Amazon + zrzut Apilo + faktura |
| **FBA** | zrzut Amazon + zrzut Apilo + faktury PL z Amazona |
| FBA **bez faktury PL** (np. wysyłka z magazynu FR/IT) | POMINIĘTE (zgodnie z ustaleniem) |
| eBay / inne platformy | tracking/Apilo + faktura z Apilo (bez Amazona) |

### 2.5. Komunikaty w logach — co znaczą

| Komunikat | Znaczenie / co robić |
|---|---|
| `Limit zapytan Apilo: 130/min` | OK — ochrona przed limitem API |
| `Rate limit (429) — czekam ...` | OK — program sam czeka i ponawia |
| `UWAGA: serwis prosi o logowanie/kod 2FA` | wpisz dane w otwartym oknie |
| `pobrano fakture ... (78 KB)` | OK — faktura ściągnięta |
| `POMINIETO ... brak faktury PL` | celowe — FBA bez polskiej faktury |
| `[diag ...]` | szczegóły techniczne — przy zgłaszaniu problemu wyślij je |
| `BLAD ...` | zamówienie się nie udało — patrz 2.6 |

### 2.6. Typowe problemy

**„Błąd połączenia z Apilo" przy starcie** — najpewniej wygasły token i kod:
wygeneruj nowy Kod autoryzacji w Apilo → wklej do `config.json` →
„Połącz z Apilo".

**Zrzuty/faktury Amazon się nie robią** — sesja wygasła: kliknij
„Zaloguj do Amazon EU" (lub USA), zaloguj się, uruchom ponownie.

**Program bardzo wolny** — to normalne (limity Apilo i Amazona). Nie przerywaj.

**Pojedyncze BLAD-y w długim runie** — uruchom ponownie z numerami tych
zamówień wpisanymi w „Numery Apilo" (patrz 2.3). Program czyści stare pliki
i robi je od nowa; nowy PDF nadpisze stary w DO_WYDRUKU.

**Coś innego** — zbierz: (1) pełny log z okna programu lub pliki logów,
(2) pliki `_DEBUG_*.png` z folderu DO_KONTROLI danego zamówienia,
(3) zrzut ekranu problemu — i wyślij do wsparcia.

### 2.7. Aktualizacja programu

Gdy dostaniesz informację o nowej wersji, w PowerShell (najpierw `cd` jak
zawsze — patrz 1.2) wklej komendę aktualizacji, którą otrzymasz. Konfiguracja
(`config.json`) i logowania (`browser_profiles`) zostają nietknięte.

---

*Dokument dla WERHE / WERKON Polska. Wersja: wrzesień 2026.*
