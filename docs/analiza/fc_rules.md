# Reguły przypisania FC: WRO5 vs XPO1 (reżim polski, 06.2024 – 08.2026)

Zakres: wszystkie linie z `lines.csv` z `month >= 2024-06` (pliki xlsx 2024-06…2026-06 oraz PDF-y Apilo 2026-07/08, które mają FC). Łącznie 4 696 linii; z tego 4 657 linii / 91 476 szt. trafiło do WRO5 lub XPO1 (reszta – 39 linii – to rzadkie FC opisane w pkt 6).

| FC | wysyłki | linie | sztuki | udział szt. | śr. szt./wysyłkę | mediana szt. |
|---|---|---|---|---|---|---|
| WRO5 (Okmiany, sortable) | 890 | 2 442 | 53 569 | 58,6 % | 60,2 | 45,5 |
| XPO1 (ID Logistics Nowa Niedrzwica, non-sortable) | 958 | 2 215 | 37 907 | 41,4 % | 39,6 | 16 |

Pliki pomocnicze (ten sam katalog): `fkey_fc.csv` (rozkład FC per fkey), `name_fc_lookup.csv` (tabela listing → FC dla narzędzia, 886 listingów), `rule_errors.csv` (wszystkie pomyłki reguły), `fc_rule.py` (reguła w Pythonie), `est.py` (estymator długości + ewaluacja).

---

## TL;DR

1. **O FC decyduje najdłuższy bok produktu (długość), próg ≈ 45 cm.** Wszystko o długości **< 400 mm idzie do WRO5** (2 236 z 2 237 linii, jedyny „wyjątek” to błąd parsera nazwy), wszystko **≥ 460 mm idzie do XPO1** (1 873 z 1 875 linii; 2 wyjątki to jedna wysyłka nowego ASIN-u z 02.12.2024). To jest klasyczny podział Amazon na *sortable* (paczka standardowa, najdłuższy bok ≤ 45 cm) i *non-sortable / oversize* (obsługiwany przez 3PL – stąd kod „X” w XPO1).
2. **Szara strefa 400–459 mm (545 linii, 8 547 szt., 11,7 % linii) nie jest losowa – zależy od konkretnego ASIN-u** (wymiary opakowania zarejestrowane w katalogu Amazon), a nie od fizycznej długości. W jej obrębie działa kilka stałych podreguł: przedłużki 400 mm, dłuta HEX28 400 mm, brzeszczoty 455 mm, świder 80×450 i szpadel 75×410 HEX30 → WRO5; dłuta SDS Plus/SDS Max 400–410 mm, dłuta i zestawy HEX/HEX30 30–50×410, szerokie szpadle 105–135 mm, świdry 40/50/60/100×450 → XPO1.
3. **Reguła końcowa** (kilka linii if/else na długość + rodzina + chwyt + szerokość) ma dokładność **99,29 % na liniach (4 624/4 657) i 99,58 % na sztukach (91 088/91 476)**; sam próg 460 mm daje 92,6 %/95,4 %, najlepszy pojedynczy próg (410 mm) 96,7 %/97,0 %. Na poziomie wysyłek (większość sztuk) 98,8 %.
4. **Stabilność w czasie: pełna.** W każdym kwartale 2024Q3–2026Q3 dokładność reguły ≥ 98,2 %. Spośród 886 różnych nazw listingów 880 (99,3 %) zawsze trafiało do jednego FC; 6 mieszanych jest wyjaśnionych (pkt 4). Żaden produkt nie „przełączył się” trwale z jednego FC na drugie, poza niemieckim szpadlem 75×410 HEX30, który do 11.2024 bywał w XPO1, a od 12.2024 jest zawsze w WRO5.
5. **Amazon nigdy nie miesza klas w jednej wysyłce.** W 0 z 1 848 wysyłek wystąpił jednocześnie produkt < 400 mm i produkt ≥ 460 mm. Gdy plan zawierał obie klasy, Amazon dzielił go na osobne wysyłki (FBA-ID) do WRO5 i XPO1 – 39 takich planów wśród 141 planów wieloprzesyłkowych (przy oknie 10 min). Dla planera: dobór „wypełniaczy” musi być ograniczony do tej samej klasy długości co produkt główny.
6. Reżim niemiecki (06.2022–05.2024) miał identyczny podział: **HAJ1 i DTM2 = sortable** (1 396 z 1 397 linii < 400 mm), **DTM1, LEJ3, STR1, DUS2, LEJ1, XSC1, XFR2, XDU2 = non-sortable** (0 linii < 400 mm na 1 837). Szara strefa zachowywała się tak samo jak w Polsce.

---

## 1. Rozkład FC per rodzina i per fkey

### 1.1 Per rodzina (family)

| family | linie | szt. | linie WRO5 | linie XPO1 | szt. WRO5 | szt. XPO1 | czystość (linie) |
|---|---|---|---|---|---|---|---|
| auger | 1124 | 23832 | 114 | 1010 | 1533 | 22299 | 0,90 |
| adapter | 853 | 22194 | 748 | 105 | 19875 | 2319 | 0,88 |
| driver_rod | 460 | 10445 | 460 | 0 | 10445 | 0 | 1,00 |
| other | 418 | 8569 | 225 | 193 | 4641 | 3928 | 0,54 |
| chisel_flat | 364 | 4150 | 149 | 215 | 1641 | 2509 | 0,59 |
| drill_bit | 442 | 4136 | 38 | 404 | 420 | 3716 | 0,91 |
| blade_jigsaw | 97 | 3954 | 97 | 0 | 3954 | 0 | 1,00 |
| extension | 180 | 3878 | 99 | 81 | 2410 | 1468 | 0,55 |
| driver_pile | 137 | 3603 | 137 | 0 | 3603 | 0 | 1,00 |
| grease | 24 | 1462 | 24 | 0 | 1462 | 0 | 1,00 |
| chisel_spade | 35 | 1102 | 29 | 6 | 918 | 184 | 0,83 |
| set_chisel | 160 | 1086 | 17 | 143 | 126 | 960 | 0,89 |
| chisel_bush | 115 | 894 | 115 | 0 | 894 | 0 | 1,00 |
| tamper | 38 | 298 | 38 | 0 | 298 | 0 | 1,00 |
| chisel_point | 37 | 297 | 8 | 29 | 36 | 261 | 0,78 |
| blade_recip | 31 | 285 | 31 | 0 | 285 | 0 | 1,00 |
| pin | 19 | 261 | 19 | 0 | 261 | 0 | 1,00 |
| chisel_gouge | 42 | 224 | 21 | 21 | 112 | 112 | 0,50 |
| spring | 26 | 212 | 26 | 0 | 212 | 0 | 1,00 |
| set_adapter | 17 | 209 | 17 | 0 | 209 | 0 | 1,00 |
| handle | 8 | 151 | 0 | 8 | 0 | 151 | 1,00 |
| string | 15 | 135 | 15 | 0 | 135 | 0 | 1,00 |
| set_drill | 13 | 91 | 13 | 0 | 91 | 0 | 1,00 |
| saw_disc | 2 | 8 | 2 | 0 | 8 | 0 | 1,00 |

Rodzina **sama w sobie nie wystarcza** – mieszane są `auger`, `adapter`, `other`, `chisel_*`, `extension`, `set_chisel`, `drill_bit`. We wszystkich tych przypadkach mieszanka rozdziela się po długości:

* `auger`: świdry ogrodowe 220/250/300/350/370 mm → WRO5 (wszystkie 114 linii WRO5 w tej rodzinie to krótkie świdry „Świder glebowy … 220/250/300 mm długości” oraz 80×450); świdry 450/600/800 mm i świdry ziemne z adapterem SDS/HEX (bez długości w nazwie, fizycznie ~80 cm) → XPO1.
* `adapter`: prawdziwe adaptery (M14, SDS, UNC, HEX; 748 linii) → WRO5. 105 linii XPO1 to **błędy normalizacji fkey**: „Przedłużenie wiercenia 1000 mm SDS Max … adaptera” (42 linie), „Przedłużenie wiertła 500 mm” (18), „1180 mm” (10), „Wiertarka/Wiertło z adapterem SDS Max 80 mm” (= świder ziemny 80 mm, 25 linii), „Zestaw świdrów Ø40/60, dł. 80 cm z adapterem SDS Plus” (4), „Wiertło do lodu 200×800 mm” (1).
* `drill_bit`: wiertła 110–260 mm → WRO5 (38 linii); 460 i 600 mm → XPO1 (404 linii).
* `extension`: 120/200/250/300/400 mm → WRO5; 500/600/750/800/1000/1180/5000 mm → XPO1.
* `chisel_flat/point/gouge/spade`, `set_chisel`: 150–300 mm → WRO5; 600 mm → XPO1; 400–440 mm → szara strefa (pkt 2.2).
* `other` (486 linii): pół na pół, bo miesza w sobie wkrętaki do gwoździ, młotki gumowe, brzeszczoty (→ WRO5) z drążkami przedłużającymi 600/1000/5000 mm i świdrami ziemnymi „Wiertło uziemiające 60 mm SDS Plus” (= Erdbohrer, → XPO1).

### 1.2 Per fkey

413 różnych kluczy fkey; 394 (95,4 %) jest w 100 % czystych, ale pokrywają one tylko 79,9 % linii, bo cztery największe klucze są mieszane – i wszystkie cztery są **artefaktami normalizacji**, nie zachowania Amazona:

| fkey | linie WRO5 | linie XPO1 | szt. WRO5 | szt. XPO1 | dlaczego mieszany |
|---|---|---|---|---|---|
| adapter\|sds_max | 145 | 95 | 3245 | 1764 | XPO1 = przedłużki 500/1000/1180 mm SDS Max i świdry 80 mm z adapterem (nazwy z „adapter”) |
| other | 114 | 95 | 2446 | 1760 | XPO1 = słupki/drążki 600/1000/5000 mm, świdry ziemne 100/180/200 mm; WRO5 = drążek 200/400 mm, brzeszczoty, wkrętaki |
| other\|sds_plus | 40 | 47 | 1055 | 1552 | XPO1 = „Wiertło uziemiające 60 mm SDS Plus”, „Wiertło wiertnicze 100 mm SDS Plus” (świdry ziemne); WRO5 = wkrętaki do gwoździ 13,5/16,5/20,2×65 |
| other\|sds_max | 22 | 27 | 127 | 415 | XPO1 = świdry ziemne 40/100 mm SDS Max, szypa 110×460; WRO5 = wkrętaki 145 mm, młotek 65×85×210 |
| chisel_spade\|d75\|l410\|hex30 | 29 | 6 | 918 | 184 | jeden ASIN; XPO1 tylko 07–11.2024, potem zawsze WRO5 |
| auger\|d40 / d60 / d80 | 6/7/13 | 23/25/26 | 80/59/87 | 458/430/430 | parser nie złapał „220/250/300 mm długości” (WRO5) vs świdry ziemne bez długości (XPO1) |
| set_chisel\|hex30\|n3 / n50, set_chisel\|sds_plus\|n50 | 6/5/4 | 4/4/5 | – | – | szara strefa 400–410 mm, różne ASIN-y (pkt 2.2) |
| auger\|d100\|l600, auger\|d80\|l600, auger\|d40\|l450 | 1/1/1 | 35/30/17 | 7/7/7 | 638/568/484 | jedna wysyłka S02612 z 02.12.2024 (pkt 4) |
| adapter\|hex | 23 | 1 | 822 | 4 | XPO1 = „Wiertło do lodu 200×800 mm … adapter HEX” |
| other\|hex30 | 5 | 12 | 43 | 94 | XPO1 = szypa 135×410, zestawy 35/50×410; WRO5 = ubijaczki 150/250 mm |
| chisel_point\|l410\|hex30, chisel_flat\|d75\|l400\|sds_max | 1/4 | 2/1 | 5/17 | 21/3 | różne ASIN-y w szarej strefie |

Największe czyste klucze: WRO5 – `adapter|sds_plus` 3 688 szt., `adapter|m14` 3 285, `adapter|m14|unf_1_2` 2 970, `blade_jigsaw|T744D|l180|n5` 2 466, `driver_pile|d20.2|l28|sds_plus` 1 948, `driver_rod|d20.2|l165|sds_max` 1 721, `grease|d100` 1 462, `adapter|unc_1_1_4` 1 441, `extension|l400` 1 348. XPO1 – `auger|d80|sds_plus` 2 571, `auger|sds_plus` 1 846, `auger|d150|sds_plus` 1 255, `auger|d60|l800|sds_plus` 887, `auger|d50|l800|sds_plus` 875, `auger|d60|l600` 874, `auger|d40|sds_plus` 817, `chisel_flat|d75|l600|sds_max` 728.

**Wniosek metodyczny:** do budowy tabeli historycznej dla narzędzia lepiej używać **nazwy listingu (lub SKU Apilo / ASIN)** niż fkey: 880 z 886 nazw jest w 100 % czystych, podczas gdy fkey „gubi” długość w ok. 20 % linii.

---

## 2. Fizyczny czynnik: długość (najdłuższy bok)

Długość `L` = `length_mm` z fkey, a gdy brak – wyciągnięta z nazwy (wzorce „NNN mm długości”, „A x B mm”, „dł. 80 cm”, „56 cm”, „AxBxC”), a gdy nadal brak – domyślna dla rodziny (świdry ziemne z adapterem SDS/HEX bez podanej długości = ~800 mm; adaptery, wbijaki, brzeszczoty, smar, sprężyny itp. = krótkie).

### 2.1 Rozkład FC po klasach długości

| klasa długości | linie | linie WRO5 | linie XPO1 | szt. | szt. WRO5 | szt. XPO1 |
|---|---|---|---|---|---|---|
| < 400 mm | 2237 | 2236 | 1 | 49239 | 49209 | 30 |
| 400–459 mm | 545 | 204 | 341 | 8547 | 4346 | 4201 |
| ≥ 460 mm | 1875 | 2 | 1873 | 33690 | 14 | 33676 |

Szczegółowo (linie WRO5 / XPO1) po długościach: 14–370 mm: 2236 / 0 (jedyna linia XPO1 „< 400” to „Wiertarka WERHE z uchwytem SDS Max, wytrzymała wiertarka 100 mm” – świder ziemny 100 mm, którego 100 mm to średnica; fizycznie ~800 mm). **400 mm: 118 / 66; 410 mm: 53 / 177; 440 mm: 0 / 11; 450 mm: 23 / 87; 455 mm: 10 / 0**; 460 mm: 0 / 103; 500: 0 / 20; 560: 0 / 24; 600: 2 / 604; 610–5000: 0 / 288.

Skan progów dla najprostszej reguły „L ≥ T → XPO1”:

| T (mm) | dokładność linie | dokładność szt. |
|---|---|---|
| 400 | 95,56 % | 95,20 % |
| **410** | **96,67 %** | **96,97 %** |
| 450 | 93,77 % | 96,78 % |
| **460** | 92,61 % | 95,36 % |
| 500 | 90,40 % | 94,40 % |
| 600 | 89,46 % | 93,52 % |

Interpretacja: granica fizyczna to **45 cm najdłuższego boku opakowania** (limit Amazon dla paczki standardowej „sortable” w EU). Produkty o nominalnej długości 400–450 mm mają opakowanie raz poniżej, raz powyżej 45 cm (np. dłuto 135×410 mm sprzedawane „w plastikowej walizce” → XPO1, a to samo 410 mm bez walizki → WRO5), dlatego o ich klasie decydują **wymiary zarejestrowane w katalogu Amazon dla danego ASIN-u**, a nie liczba z tytułu.

### 2.2 Szara strefa 400–459 mm – każda grupa z liczbami

| grupa | linie WRO5 | linie XPO1 | szt. WRO5 | szt. XPO1 | okres | reguła |
|---|---|---|---|---|---|---|
| przedłużki 400 mm (do świdra, słupek 400) | 46 | 0 | 1521 | 0 | 2024-06…2026-08 | WRO5 |
| dłuta HEX28 28/35/50/75 × 400 mm | 62 | 0 | 478 | 0 | 2024-08…2026-08 | WRO5 |
| brzeszczoty szablaste 455 mm (S2243HM itp.) | 10 | 0 | 145 | 0 | 2024-09…2026-05 | WRO5 |
| świder ogrodowy 80 × 450 | 22 | 0 | 464 | 0 | 2024-12…2026-06 | WRO5 |
| szpadel 75 × 410 HEX30 (Spatmeißel / Spade Sisel / „75x410 Hex 30mm”) | 40 | 6 | 1578 | 184 | 2024-06…2026-08 | WRO5 (XPO1 tylko 07–11.2024) |
| świdry ogrodowe 40/50/60/100 × 450 | 1 | 83 | 7 | 1852 | 2024-12…2026-08 | XPO1 |
| szerokie dłuta/szypy ≥ 105 mm × 410–440 (135×410 HEX30, 135×410 HEX28, 110×410 SDS Max, 105×440 SDS Max, 135×440 HEX30) | 0 | 64 | 0 | 854 | 2024-06…2026-06 | XPO1 |
| dłuta i zestawy HEX / HEX30 30–50 × 410 (szpic, płaskie, zestawy 2–3 szt.) | 13 | 124 | 56 | 844 | 2024-06…2026-08 | XPO1 |
| dłuta i zestawy SDS Plus 400 (20×400, 50×400, szpic 400, bruzdownik 60×400, zestawy 400 3-cz.) | 6 | 45 | 80 | 387 | 2024-06…2026-08 | XPO1 |
| dłuta i zestawy SDS Max 400–410 (25/50/75×400, bruzdownik 60×400, zestawy 400) | 4 | 23 | 17 | 102 | 2024-12…2026-08 | XPO1 |

Uwagi:

* **Świder 80×450 → WRO5, ale 40/50/60/100×450 → XPO1.** To nie jest błąd danych: 22 linie w 6 kwartałach, zawsze WRO5, w tym samym czasie gdy 60×450 (19 linii) i 100×450 (23 linie) szły do XPO1. Jedyne sensowne wyjaśnienie to inne wymiary opakowania wpisane dla tego ASIN-u. Waga nie jest czynnikiem (80×450 jest cięższy niż 60×450, a idzie do „lżejszego” FC).
* **HEX28 400 mm → WRO5 (62/62), ale SDS Plus/Max 400 mm → XPO1 (68/78).** Ta sama nominalna długość, inne FC – znowu per ASIN. Wyjątki WRO5 wśród SDS: „WERKON Profi SDS Max dłuto płaskie 75×400” (3 linie, 12.2025–05.2026, zawsze WRO5), „Dłuto do betonu 75x400 sds max” (1), „Zestaw Dłut, Szpic, 25, 50 × 400mm SDS PLUS” (4 linie, 07–08.2026, zawsze WRO5), „WERHE zestaw dłut SDS Plus, 400 mm, 3-częściowy” (2).
* **HEX/HEX30 30–50×410 → XPO1 (124/137).** 13 linii WRO5 to trzy nowe listingi zestawów z 2026 („Profesjonalne dłuto SDS HEX zestaw 3-częściowy 35,50 x 410” – 5 linii WRO5 w 04–05.2026 po 2 liniach XPO1 w 02–03.2026; „WERKON zestaw dłut SDS Hex 3-częściowy, 410 mm” – 3; „Zestaw szpic, 35, 50x410 Hex30” – 3 WRO5 / 3 XPO1 w 07–08.2026) oraz dwa pojedyncze („Dłuto Szpic kręcony Hex30 x410mm”, „Samoostrzący szpicak 410 mm HEX30”). Zestaw „Zestaw szpic, 35, 50x410 Hex30” jest jedynym listingiem, który w tym samym miesiącu szedł do obu FC (07.2026: 2 W / 1 X; 08.2026: 1 W / 2 X) – prawdopodobnie zestaw ma dwa ASIN-y/warianty o różnych wymiarach; warto to sprawdzić w Seller Central.

### 2.3 Inne cechy (średnica, chwyt, zestaw/liczba sztuk)

* **Chwyt (shank)** nie rozdziela FC sam w sobie: SDS Plus 40→WRO5/47→XPO1 w `other|sds_plus`, SDS Max podobnie. Działa tylko jako podreguła w szarej strefie (HEX28 400 → WRO5; SDS 400 → XPO1; HEX/HEX30 410 → XPO1).
* **Średnica / szerokość** działa tylko w szarej strefie: szerokie szpadle ≥ 105 mm przy 410–440 mm zawsze XPO1 (64/64), 75 mm × 410 HEX30 → WRO5, 80 mm × 450 → WRO5.
* **Zestawy / count**: zestawy brzeszczotów (n5, n10), zestawy wierteł 210 mm, zestawy adapterów → WRO5 (krótkie). Zestawy dłut idą tam, gdzie ich długość (400/410 → XPO1 z wyjątkami wyżej; 600 → XPO1; 100 % zestawów 600 mm w XPO1).
* **Podwójna spirala („dbl”), „Profi/Professional”, marka WERHE/WERKON** – bez znaczenia.

---

## 3. Reguła decyzyjna i jej dokładność

```
L = najdłuższy bok produktu w mm (długość nominalna z tytułu / katalogu)

if L >= 460:                      -> XPO1        # non-sortable
elif L < 400:                     -> WRO5        # sortable
else:  # szara strefa 400–459 mm
    if brzeszczot (blade_recip/blade_jigsaw):            -> WRO5   # 455 mm brzeszczoty szablaste
    if przedłużka / słupek 400 mm (extension):            -> WRO5
    if dłuto o szerokości >= 105 mm (szypa 135x410 itp.): -> XPO1   # sprzedawane w walizce
    if chwyt HEX28:                                       -> WRO5
    if świder ogrodowy: 80x450 -> WRO5, pozostałe x450    -> XPO1
    if szpadel 75x410 HEX30:                              -> WRO5
    else (dłuta SDS Plus/Max 400–410, HEX/HEX30 30–50x410, zestawy 410): -> XPO1
brak wymiaru: świdry ziemne (auger) i uchwyty (handle) -> XPO1, wszystko inne -> WRO5
```

Kod: `fc_rule.py` (funkcja `predict_fc(family, shank, diameter_mm, L, name)`).

**Dokładność (reżim polski, tylko linie WRO5/XPO1):**

| wariant | linie | sztuki |
|---|---|---|
| tylko próg 460 mm | 92,61 % (4 313/4 657) | 95,36 % (87 231/91 476) |
| tylko próg 410 mm | 96,67 % (4 502/4 657) | 96,97 % |
| **reguła końcowa** | **99,29 % (4 624/4 657)** | **99,58 % (91 088/91 476)** |
| reguła końcowa, poziom wysyłki (większość sztuk) | 98,81 % (1 826/1 848 wysyłek) | – |

Macierz pomyłek reguły końcowej – linie:

| rzeczywiste \ przewidziane | WRO5 | XPO1 | razem |
|---|---|---|---|
| WRO5 | 2416 | 26 | 2442 |
| XPO1 | 7 | 2208 | 2215 |
| razem | 2423 | 2234 | 4657 |

Macierz pomyłek – sztuki:

| rzeczywiste \ przewidziane | WRO5 | XPO1 | razem |
|---|---|---|---|
| WRO5 | 53395 | 174 | 53569 |
| XPO1 | 214 | 37693 | 37907 |
| razem | 53609 | 37867 | 91476 |

Macierz pomyłek na poziomie wysyłek (1 848): WRO5 → 872 dobrze / 18 źle; XPO1 → 954 dobrze / 4 źle.

**Wszystkie 33 błędne linie (392 szt.)** – każda to konkretny listing, którego można się nauczyć z tabeli `name_fc_lookup.csv`:

| listing | L mm | FC rzeczywisty | reguła | linie | szt. | miesiące |
|---|---|---|---|---|---|---|
| WERHE ® Profi SDS HEX Spatmeißel 75 x 410 mm (DE) | 410 | XPO1 | WRO5 | 6 | 184 | 2024-07, 2024-08, 2024-11 |
| Profesjonalne dłuto SDS HEX zestaw 3-częściowy 35,50 x 410 mm | 410 | WRO5 | XPO1 | 5 | 20 | 2026-04, 2026-05 |
| Zestaw Dłut, Szpic, 25, 50 x 400mm SDS PLUS | 400 | WRO5 | XPO1 | 4 | 50 | 2026-07, 2026-08 |
| WERKON zestaw dłut SDS Hex 3-częściowy, 410 mm | 410 | WRO5 | XPO1 | 3 | 14 | 2026-06 |
| WERKON Profi SDS Max dłuto płaskie 75 x 400 mm | 400 | WRO5 | XPO1 | 3 | 14 | 2025-12, 2026-03, 2026-05 |
| Zestaw szpic, 35, 50x410 Hex30 | 410 | WRO5 | XPO1 | 3 | 12 | 2026-07, 2026-08 |
| WERHE zestaw dłut SDS Plus, 400 mm, 3-częściowy | 400 | WRO5 | XPO1 | 2 | 30 | 2026-06 |
| Dłuto do betonu 75x400 sds max | 400 | WRO5 | XPO1 | 1 | 3 | 2026-08 |
| Świder glebowy 80 mm Ø, 600 mm (S02612) | 600 | WRO5 | XPO1 | 1 | 7 | 2024-12 |
| Świder glebowy 100 mm Ø, 600 mm (S02612) | 600 | WRO5 | XPO1 | 1 | 7 | 2024-12 |
| Świder glebowy 40 mm Ø, 450 mm (S02612) | 450 | WRO5 | XPO1 | 1 | 7 | 2024-12 |
| Dłuto Szpic kręcony Hex30 x410mm | 410 | WRO5 | XPO1 | 1 | 5 | 2026-07 |
| Wiertarka WERHE z uchwytem SDS Max, wytrzymała wiertarka 100 mm (świder ziemny, błąd parsera) | 100 | XPO1 | WRO5 | 1 | 30 | 2025-09 |
| WERHE Samoostrzący szpicak 410 mm HEX30 | 410 | WRO5 | XPO1 | 1 | 5 | 2026-02 |

**Rekomendacja dla narzędzia:** (1) najpierw tabela historyczna listing/SKU → FC (`name_fc_lookup.csv`, kolumny `fc_dominant`, `fc_last`, `purity`); (2) reguła powyżej tylko dla produktów bez historii; (3) produkty z szarej strefy bez historii oznaczać jako „niepewne” (bazowo 63 % XPO1) i nie używać ich jako wypełniaczy, dopóki nie pojawi się pierwsza wysyłka.

---

## 4. Stabilność w czasie (2024Q2/Q3 – 2026Q3)

| kwartał | linie | szt. | linie WRO5 | linie XPO1 | dokł. reguły (linie) | dokł. reguły (szt.) | sam próg 460 (linie) |
|---|---|---|---|---|---|---|---|
| 2024Q2 (czerwiec) | 120 | 3318 | 69 | 51 | 100,00 % | 100,00 % | 95,00 % |
| 2024Q3 | 377 | 7632 | 187 | 190 | 98,94 % | 97,88 % | 92,84 % |
| 2024Q4 | 340 | 5772 | 144 | 196 | 98,53 % | 99,26 % | 91,76 % |
| 2025Q1 | 533 | 10503 | 257 | 276 | 100,00 % | 100,00 % | 92,50 % |
| 2025Q2 | 458 | 10458 | 220 | 238 | 100,00 % | 100,00 % | 92,36 % |
| 2025Q3 | 538 | 10130 | 315 | 223 | 99,81 % | 99,70 % | 93,49 % |
| 2025Q4 | 480 | 6797 | 286 | 194 | 99,79 % | 99,97 % | 92,08 % |
| 2026Q1 | 597 | 10519 | 336 | 261 | 99,66 % | 99,90 % | 91,46 % |
| 2026Q2 | 710 | 16204 | 371 | 339 | 98,45 % | 99,56 % | 92,25 % |
| 2026Q3 (lipiec–sierpień, PDF) | 504 | 10143 | 257 | 247 | 98,21 % | 99,31 % | 94,25 % |

Reguła trzyma się w każdym kwartale; drobny spadek w 2026Q2–Q3 to nowe listingi zestawów HEX30 410 (pkt 2.2). Podreguły szarej strefy są stałe przez cały okres (HEX28 400 → WRO5 w każdym z 9 kwartałów, świder 80×450 → WRO5 w 6 kwartałach, szerokie szpadle → XPO1 w 9 kwartałach, świdry x450 → XPO1 w 8 kwartałach).

**Produkty, które zmieniły FC** (6 z 886 nazw ma oba FC):

1. „WERHE ® Profi SDS HEX Spatmeißel 75 x 410 mm” (niemiecki listing szpadla): 06.2024 WRO5 (3), 07.2024 XPO1 (3), 08.2024 WRO5 2 / XPO1 1, 09.2024 WRO5, 11.2024 XPO1 (2), od 12.2024 do 01.2026 wyłącznie WRO5 (23 linie). W reżimie niemieckim ten sam listing szedł do non-sortable (DTM1/LEJ3/STR1). Jedyny prawdziwy „switch”: **od 12.2024 traktować jako WRO5**.
2. „Świder glebowy 40×450”, „80×600”, „100×600”: po jednej linii WRO5 w **S02612 z 02.12.2024** – była to trzecia z rzędu wysyłka nowo wprowadzonej serii świdrów ogrodowych (S02610, S02611 z krótkimi świdrami 220–370 mm → WRO5, potem S02612 z 450/600 mm → też WRO5). Od 01.2025 te same listingi trafiały 34, 30 i 17 razy do XPO1 (0 razy do WRO5). Hipoteza: nowy ASIN bez zweryfikowanych wymiarów w katalogu jest przy pierwszej wysyłce kierowany jak „sortable”; po pomiarze w FC klasa się zmienia. **Dla narzędzia: nowe długie ASIN-y przy pierwszej wysyłce mogą pójść do WRO5.**
3. „Profesjonalne dłuto SDS HEX zestaw 3-częściowy 35,50 x 410 mm”: 02–03.2026 XPO1 (2), 04–05.2026 WRO5 (5) – zmiana w drugą stronę (możliwa korekta wymiarów w katalogu).
4. „Zestaw szpic, 35, 50x410 Hex30”: 07–08.2026 3 W / 3 X (patrz 2.2).

Udziały FC w liniach są stabilne (WRO5 45–58 % w zależności od kwartału, zależnie od miksu produktów) – nie widać żadnego momentu, w którym Amazon zmieniłby politykę routingu.

---

## 5. Wysyłki mieszane

**Wewnątrz jednej wysyłki:** w **0 z 1 848** wysyłek WRO5/XPO1 wystąpiła jednocześnie linia < 400 mm i linia ≥ 460 mm (753 wysyłek zawiera produkty krótkie, 783 długie, przecięcie puste). Produkty z szarej strefy występują razem z krótkimi (59 wysyłek, wszystkie do WRO5 – są to HEX28 400, przedłużki 400, 75×400 WERKON itp.) i razem z długimi (95 wysyłek, 94 do XPO1 + S02612) – zawsze zgodnie z klasą danego ASIN-u. 13 wysyłek, w których reguła przewiduje dwa FC, to w całości: 6 przypadków per-ASIN z tabeli błędów, 3 wysyłki S02612/S02397/S02452 (opisane wyżej), 2 błędy estymatora długości (adapter Stihl w rodzinie „auger”, świder „wiertarka 100 mm”) i 2 z PDF-ów 07–08.2026 (dłuto 410 HEX30 / 75×400 SDS Max w paczkach do WRO5). **Amazon nie tworzy wysyłek mieszanych; klasa jest cechą ASIN-u.**

**Na poziomie planu Send-to-Amazon** (pliki xlsx 06.2024–06.2026, 1 640 wysyłek; plan = wysyłki z tego samego pliku utworzone w odstępie ≤ 10 min):

| okno | plany | plany wieloprzesyłkowe | plany z WRO5 **i** XPO1 | plany wieloprzesyłkowe w jednym FC |
|---|---|---|---|---|
| ≤ 5 min | 1615 | 25 | 2 (8 %) | 23 |
| **≤ 10 min** | **1465** | **141** | **39 (27,7 %)** | **102** (61 XPO1, 39 WRO5, 1 HAJ1, 1 DTM1) |
| ≤ 30 min | 977 | 328 | 174 (53 %) | 154 |

Wzorzec: pracownik tworzy plan, Amazon dzieli go na osobne FBA-ID per FC (w 27 z 39 planów dokładnie 1 wysyłka WRO5 + 1 XPO1; w pozostałych 2–3 wysyłki do jednego z FC), a każda wysyłka ma czysto jednorodną zawartość. Przykłady: 22.01.2025 13:45 – S02665 WRO5 (5 linii, 35 szt.) i S02666 XPO1 (4 linie, 35 szt.) utworzone w tej samej minucie; 17.04.2025 08:30/08:39 – S02880 WRO5 (6 linii, 73 szt.) + S02881 XPO1 (1 linia, 21 szt.). 102 plany wieloprzesyłkowe w jednym FC to ręczne dzielenie „jedna wysyłka = jedna paczka/karton” przez pracownika (52,7 % wszystkich wysyłek ma tylko 1 linię; XPO1: 597 z 958 jednoliniowych).

**PDF-y Apilo 07–08.2026 (jedyne źródło z rozróżnieniem palety/paczki):** 224 wysyłki: „Palety Amazon” 22 (19 XPO1 – 2 833 szt., 3 WRO5 – 467 szt.; śr. 149 szt. i 5,7 linii na paletę do XPO1), „Paczki FBA” 198 (102 WRO5 – 5 248 szt., śr. 51,5 szt./paczkę, max 200; 96 XPO1 – 1 426 szt., śr. 14,9 szt./paczkę, max 50), „AMAZON USA” 3, „WERHE DANIEL” 1. **Palety jadą praktycznie tylko do XPO1; paczki do XPO1 są małe (mediana 14 szt.), paczki do WRO5 duże (mediana 40 szt.).**

Konsekwencje dla planera: (a) przewidywać FC per linia i grupować plan na dwie „połówki” – Amazon i tak je rozdzieli; (b) wypełniacze dla palety do XPO1 muszą być produktami klasy ≥ 460 mm (lub z szarej strefy o potwierdzonym XPO1), wypełniacze dla kartonów do WRO5 – klasy < 400 mm (lub HEX28 400, przedłużki 400 itd.); (c) nie ma sensu optymalizować „wspólnej” palety WRO5+XPO1.

---

## 6. Rzadkie FC po 06.2024 (i wcześniejsze egzotyczne)

| FC | wysyłki / linie / szt. | daty | co to jest |
|---|---|---|---|
| HAJ1, DTM1, DTM2, DUS2, LEJ3 | 11 wysyłek / 12 linii / 194 szt. | 04.06.2024 – 17.09.2024 | Ogon reżimu niemieckiego: wszystkie linie to **listingi niemieckojęzyczne** (Bohrverlängerung 500/1000 mm, Erdbohrer 50 mm, Verlängerung 200 mm UNC, Pfosten Driver, Verlängerung Erdbohrer 400 mm) – plany zakładane z amazon.de, kierowane jeszcze do niemieckich FC. Pierwsza polska wysyłka: 06.06.2024 (S02336 XPO1), ostatnia niemiecka: 17.09.2024 (S02499 LEJ3). Po 09.2024 zjawisko nie występuje. |
| WRO2 (Bielany Wrocławskie) | 2 wysyłki / 12 linii / 195 szt. | 08–09.10.2024 | Sortable FC koło Wrocławia; wyłącznie krótkie produkty (adaptery Stihl/M14/SDS, wbijak 13,5×35, sworznie, brzeszczoty T544D, wkrętak 145 mm). Jednorazowy „overflow” WRO5 w tym tygodniu; traktować jak WRO5. |
| POZ1 (Sady k. Poznania) | 1 wysyłka / 4 linie / 43 szt. | 09.10.2024 | Sortable; krótkie produkty (wbijak 10,5×14, wbijak 20,2×35 HEX, przedłużka M14 120 mm, zestaw wierteł 210 mm). Ten sam tydzień co WRO2 – ta sama sytuacja. |
| BHX4 (Coalville, UK) | 1 wysyłka / 10 linii / 85 szt. | 20.11.2024 | Wysyłka do amazon.co.uk (angielskie tytuły: adaptery, peg driver, jigsaw blades, auger adaptor Stihl). Nie należy do polskiego routingu. |
| XWR3 | 1 wysyłka / 1 linia / 3 szt. | 11.07.2024 | 3PL (kod „X”) w rejonie Wrocławia dla ładunków specjalnych: „drążek przedłużający 5000 mm”. Późniejsze wysyłki tego samego 5-metrowego drążka (24 linie) szły już do XPO1. |
| LBA4 (Świebodzin) | 1 wysyłka / 9 linii / 45 szt. | 05.08.2021 | Sprzed rejestrowania FC; angielskie tytuły (UK). Jedyna wysyłka z FC w 2021 r. |
| XDEA, XGEB | 1 + 2 wysyłki, po 19 szt. | 02.2024, 04.2024, 05.2024 | Niemieckie 3PL non-sortable; wyłącznie „Bohrverlängerung 500 mm SDS Max”. |
| CDG7 (Lauwin-Planque, FR) | 1 wysyłka / 45 szt. | 01.03.2024 | Francuski listing adaptera UNC → amazon.fr. |

W reżimie polskim (od 06.2024) realne są tylko WRO5 i XPO1 – 1 848 z 1 864 wysyłek (99,1 %).

---

## 7. Reżim niemiecki (06.2022 – 05.2024) – analogiczny podział

3 381 linii z FC (60 289 szt.). Ten sam estymator długości:

| grupa FC | linie < 400 | linie 400–459 | linie ≥ 460 | szt. < 400 | szt. 400–459 | szt. ≥ 460 |
|---|---|---|---|---|---|---|
| **sortable: HAJ1 (951 linii), DTM2 (593)** | 1396 | 50 | 98* | 32072 | 984 | 1466* |
| **non-sortable: DTM1 (501), LEJ3 (492), STR1 (381), DUS2 (136), XSC1 (134), LEJ1 (118), XFR2 (36), XDU2 (35), XGEB (2), XDEA (1)** | 0 | 249 | 1587 | 0 | 2989 | 22733 |

\* 98 „długich” linii w HAJ1/DTM2 to w całości artefakt fkey: „Erdbohrer Adapter passend für Stihl” (44 linie) i „SchnellwechselBolzen für Erdbohrer” (25) mają rodzinę `auger`, więc dostały domyślne 800 mm – fizycznie to adaptery i sworznie < 20 cm. Po ich poprawieniu podział jest **idealny: 0 linii < 400 mm w non-sortable, 0 linii ≥ 460 mm w sortable.**

Odpowiedniki: **HAJ1/DTM2 ↔ WRO5**, **DTM1/LEJ3/STR1/DUS2/LEJ1/XSC1/XFR2/XDU2 ↔ XPO1**. Zmiany w czasie dotyczyły tylko tego, *który* FC z danej grupy był używany: 2022Q3–Q4 DTM2 + STR1/DUS2; 2023Q1–Q3 HAJ1 + LEJ3/STR1/LEJ1/XSC1 (XSC1 = 3PL, 95 linii w 2023Q2); 2023Q4–2024Q2 HAJ1/DTM2 + DTM1/LEJ3. Ostatnia wysyłka głównego strumienia do DE: 29.05.2024; pierwsza do PL: 06.06.2024.

Szara strefa w DE zachowywała się identycznie jak w PL: przedłużki 400 mm → sortable (DTM2 10, HAJ1 18; 0 non-sortable), dłuta HEX28 400 → sortable (12 linii; 0 non-sortable), dłuta HEX30 410 → non-sortable (95 linii; 0 sortable), dłuta SDS Plus/Max 400–410 → non-sortable (49 linii), zestawy dłut SDS Plus 400 → non-sortable (18). Jedyna różnica: szpadel 75×410 HEX30 w DE był non-sortable (48 linii), w PL od 12.2024 jest WRO5. To potwierdza, że klasa wynika z wymiarów katalogowych ASIN-u, a próg ~45 cm jest ogólnoeuropejski.

---

## 8. Parametry do narzędzia

* `threshold_mm = 460` (≥ 460 → XPO1); `gray_zone = [400, 459]`; `< 400 → WRO5`.
* dokładność reguły końcowej: linie 0,9929 (4 624/4 657), sztuki 0,9958 (91 088/91 476), wysyłki 0,9881 (1 826/1 848).
* dokładność samego progu 460: linie 0,9261, sztuki 0,9536; samego progu 410: linie 0,9667, sztuki 0,9697.
* podreguły szarej strefy → WRO5: przedłużki 400 mm, dłuta HEX28 400 mm, brzeszczoty 455 mm, świder 80×450, szpadel 75×410 HEX30; → XPO1: dłuta o szerokości ≥ 105 mm (410–440), świdry 40/50/60/100×450, dłuta i zestawy SDS Plus/Max 400–410, dłuta i zestawy HEX/HEX30 30–50×410.
* wyjątki per listing (do tabeli lookup, nie do reguły): „WERKON Profi SDS Max dłuto płaskie 75 x 400 mm” → WRO5; „Zestaw Dłut, Szpic, 25, 50 x 400mm SDS PLUS” → WRO5; „WERHE zestaw dłut SDS Plus, 400 mm, 3-częściowy” → WRO5; „WERKON zestaw dłut SDS Hex 3-częściowy, 410 mm” → WRO5; „Profesjonalne dłuto SDS HEX zestaw 3-częściowy 35,50 x 410 mm” → ostatnio WRO5; „Zestaw szpic, 35, 50x410 Hex30” → 50/50 (sprawdzić ASIN); „Dłuto Szpic kręcony Hex30 x410mm”, „Samoostrzący szpicak 410 mm HEX30”, „Dłuto do betonu 75x400 sds max” → WRO5 (po 1 obserwacji); „Spatmeißel 75 x 410 mm” (DE) → WRO5 od 12.2024.
* fkey jest niewiarygodny dla ~20 % linii (`adapter|sds_max`, `other*`, `auger|d40/d60/d80`) – narzędzie powinno indeksować historię po nazwie listingu / SKU Apilo / ASIN, a długość brać z katalogu produktów, nie z regexu.
