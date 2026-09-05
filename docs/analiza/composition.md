# Skład i wielkość wysyłek FBA – analiza kompozycji (2020-09 … 2026-08)

Źródło: `shipments.csv` (4192 wysyłek), `lines.csv` (10741 linii), `apilo_catalog.csv`. Skrypty i surowe wyniki: `analysis/a1_dist.txt`, `a2_plans.txt`, `a3_cartons.txt`, `a4_mix.txt`, `a5_pallets.txt`, `a6_monthly.txt`, `a6b_season.txt`, `a6c_season2.txt`, `a7_extra.txt`, tabele `top60_cartons.csv`, `top60_cartons2.csv`.

## 0. Zakres, definicje i zastrzeżenia

* **Reżimy:** do 2022-05 brak FC; 2022-06 … 2024-05 magazyny niemieckie (HAJ1, DTM2, DTM1, LEJ3, STR1, DUS2 …); od **2024-06 reżim polski – WRO5 (890 wysyłek) i XPO1 (958 wysyłek)**, pozostałe FC w tym okresie to 16 wysyłek marginalnych (HAJ1 4, DTM1 3, LEJ3 2, WRO2 2, DTM2/DUS2/POZ1/BHX4/XWR3 po 1). Analizy „reżimu polskiego” obejmują 2024-06 … 2026-08 i tylko WRO5/XPO1, chyba że zaznaczono inaczej.
* **Typ wysyłki (paleta / paczka)** znany jest **wyłącznie** dla plików PDF 2026-07 i 2026-08 (224 wysyłki: 198 „Paczki FBA”, 22 „Palety Amazon”, 3 „AMAZON USA”, 1 „WERHE DANIEL”). Dla PDF nie ma godziny utworzenia (data = 1. dzień miesiąca), ale jest `reference_id` (numer dokumentu Apilo, np. `AF260706556`, `PF260706014`) – numer rośnie w czasie, więc służy jako zastępcza oś czasu.
* `created_at` w plikach docx/xlsx ma rozdzielczość minutową (0 wpisów z sekundami), jest to najprawdopodobniej moment wpisania wysyłki do arkusza przez pracownika, nie czas utworzenia w Seller Central.
* `fkey` jest kluczem przybliżonym (regex); kilka kluczy jest zbiorczych (`other`, `other|sds_plus`, `adapter|sds_max`, `auger|sds_plus`, `auger`, `auger|sds_max`) – w tabelach oznaczam je jako „klucz zbiorczy”. 13 linii bez ilości pominięto w statystykach ilości.
* Skróty: p10/p25/p50/p75/p90 = percentyle; „szt.” = jednostki (units); „linia” = pozycja produktowa w wysyłce.

---

## 1. Rozkład sztuk i linii na wysyłkę

### 1.1 Po latach (wszystkie FC)

| Rok | n wysyłek | szt. średnia | p10 | p25 | **p50** | p75 | p90 | p95 | max | linie p50 | linie p75 | linie p90 | linie max | % wysyłek 1-liniowych |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2020 (od IX) | 255 | 38,6 | 3 | 8 | **17** | 46,5 | 110 | 152 | 330 | 1 | 2 | 2 | 14 | 73,7 |
| 2021 | 435 | 60,0 | 6 | 10 | **28** | 76,5 | 155 | 198 | 1085 | 1 | 2,5 | 7 | 25 | 53,6 |
| 2022 | 634 | 49,5 | 6 | 12 | **23** | 63 | 155 | 169 | 319 | 2 | 3 | 6 | 24 | 46,2 |
| 2023 | 705 | 50,3 | 6 | 10 | **24** | 67 | 145 | 168 | 351 | 2 | 3 | 6 | 17 | 42,7 |
| 2024 | 627 | 51,3 | 7 | 11 | **28** | 70 | 145 | 166 | 260 | 2 | 3 | 6 | 16 | 48,2 |
| 2025 | 766 | 49,5 | 7 | 13 | **28** | 64 | 134 | 170 | 250 | 1 | 4 | 6 | 14 | 52,3 |
| 2026 (do VIII) | 770 | 47,9 | 7 | 10 | **25** | 64,5 | 130 | 172 | 247 | 1 | 3 | 5 | 10 | 55,7 |

Rozkład jest silnie prawoskośny i **dwumodalny**: połowa wysyłek ma ≤ 25–28 szt. (pojedyncze paczki), ale 17–20 % ma ≥ 100 szt. (2024: 18,8 %, 2025: 16,3 %, 2026: 17,3 %) i tylko 2–2,5 % ma ≥ 200 szt. Maksimum w reżimie polskim to 250 szt. (WRO5) i 247 szt. (XPO1). Liczba odrębnych produktów (`fkey`) na wysyłkę: mediana 1, p75 3, p90 5–6, max 13 (2026).

### 1.2 Reżim polski (2024-06 … 2026-08) – WRO5 vs XPO1

| FC | n | szt. średnia | p10 | p25 | **p50** | p75 | p90 | p95 | max | moda | linie p50 / p75 / p90 | fkey p50 / p75 / p90 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **WRO5** | 890 | 60,2 | 9,9 | 25 | **45,5** | 85 | 133 | 170 | 250 | 10 | 2 / 4 / 6 | 2 / 4 / 5 |
| **XPO1** | 958 | 39,6 | 6 | 10 | **16** | 30 | 138 | 174 | 247 | 14 | 1 / 3 / 6 | 1 / 3 / 5 |

Po latach (mediana szt.): WRO5 2024: 54,5 → 2025: 50 → 2026: 41; XPO1 stabilnie 17 / 16 / 17. Mediana linii: WRO5 2 (wszystkie lata), XPO1 1.

Histogram sztuk na wysyłkę (liczba wysyłek):

| szt. | (0,5] | (5,10] | (10,20] | (20,30] | (30,40] | (40,60] | (60,80] | (80,100] | (100,150] | (150,200] | (200,300] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WRO5 | 40 | 99 | 70 | 76 | 126 | 154 | 86 | 79 | 96 | 54 | 10 |
| XPO1 | 44 | 232 | 294 | 151 | 38 | 34 | 12 | 14 | 65 | 47 | 27 |

Histogram liczby linii: WRO5 1 linia 377 (42 %), 2: 138, 3: 109, 4: 93, 5: 71, 6: 47, 7: 24, 8+: 31; XPO1 1 linia 597 (62 %), 2: 102, 3: 57, 4: 54, 5: 49, 6: 37, 7: 20, 8+: 42.

Interpretacja: **XPO1 jest wyraźnie dwumodalne** – 71 % wysyłek to małe paczki 5–30 szt. (zwykle 1 produkt), a 14,5 % (139/958) to duże wysyłki ≥ 100 szt. o 5–14 liniach – to są palety (potwierdzenie w §5). **WRO5** ma jeden szeroki garb 20–100 szt. (mediana 45,5) – paczki wieloproduktowe z drobnymi artykułami (adaptery, pobijaki, brzeszczoty), a wysyłki ≥ 100 szt. na WRO5 (160 = 18 %) to głównie duże paczki, nie palety (w 2026-07/08 tylko 3 z 24 wysyłek WRO5 ≥ 80 szt. to palety).

Mediana sztuk wg liczby linii i FC (reżim polski): 1 linia – WRO5 25 / XPO1 13; 2 – 55 / 22; 3 – 60 / 27; 4 – 70 / 37,5; 5 – 75 / 108; 6 – 78 / 128; 7 – 86,5 / 153,5; 8+ – 86 / 179. Na XPO1 wysyłka ≥ 5 linii to niemal na pewno paleta (skok mediany z 37,5 na 108 szt.).

Dla porównania reżim niemiecki (mediana szt.): HAJ1 58 (n 334), DTM2 33 (232), LEJ3 20,5 (178), STR1 16 (145), DUS2 16 (73), DTM1 12 (187), XSC1 23 (39), XFR2 10 (23) – wtedy też istniał podział „duży FC / małe FC”.

### 1.3 2026-07/08 wg typu (jedyne miesiące ze znanym typem)

| Typ | n | szt. średnia | min | p10 | p25 | **p50** | p75 | p90 | max | linie p50 (min–max) | fkey p50 (min–max) | szt./linię p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Paczki FBA** | 198 | 33,7 | 2 | 5 | 10 | **20** | 45 | 89 | 200 | 1 (1–9) | 1 (1–7) | 14 |
| – WRO5 | 102 | 51,5 | 2 | 6 | 15 | **40** | 69 | 112 | 200 | 1 | 1 | – |
| – XPO1 | 96 | 14,9 | 4 | 5 | 7 | **14** | 20 | 25,5 | 50 | 1 | 1 | – |
| **Palety Amazon** | 22 | 150,0 | 80 | 106 | 126 | **148,5** | 173,5 | 197 | 210 | 6 (3–7) | 4 (2–5) | 25 (IQR 21,6–33,4) |
| – WRO5 | 3 | 155,7 | 125 | – | – | 170 | – | – | 172 | 4–5 | 3–5 | – |
| – XPO1 | 19 | 149,1 | 80 | 105 | 124,5 | **138** | 176 | 199 | 210 | 6 | 4 | – |
| AMAZON USA | 3 | 24,7 | 14 | – | – | 26 | – | – | 34 | 1 | 1 | – |
| WERHE DANIEL | 1 | 95 | – | – | – | – | – | – | – | 4 | 4 | – |

Sumy: paczki 6674 szt. (WRO5 5248, XPO1 1426), palety 3300 szt. (XPO1 2833, WRO5 467). Palety = 10 % wysyłek, ale 33 % sztuk (2026-07: 1655/5087; 2026-08: 1645/5056). W obu miesiącach było **dokładnie 11 palet**, 19 z 22 poszło do XPO1.

Histogram paczek 2026-07/08: XPO1 – (0,5] 11, (5,10] 32, (10,20] 35, (20,30] 14, (30,40] 2, (40,60] 2, brak > 50; WRO5 – (0,5] 10, (5,10] 10, (10,20] 9, (20,30] 9, (30,40] 14, (40,60] 21, (60,80] 8, (80,100] 8, (100,150] 9, (150,200] 4.

**Typowe wartości do parametryzacji:** paczka na XPO1 = 14 szt. (7–20) jednego produktu; paczka na WRO5 = 40 szt. (15–69), 1–5 produktów; paleta = 150 szt. (125–175), 6 linii, 4 produkty, ~25 szt. na linię.

---

## 2. Rekonstrukcja planów (Send-to-Amazon) z czasu utworzenia

### 2.1 Metoda i jej granice

Klastrowanie łańcuchowe: ten sam `source_file`, wysyłki posortowane po `created_at`, nowy plan gdy odstęp od poprzedniej > 10 min. Pliki PDF (2026-07/08) nie mają godziny – dla nich osobno klastrowanie po numerze `reference_id` (§2.5).

Rozkład odstępów między kolejnymi wysyłkami w pliku (reżim polski, xlsx, n = 1615 odstępów): 0 min: 7; (0,2]: 1; (2,3]: 0; (3,5]: 17; (5,10]: 150; (10,15]: 173; (15,30]: 315; (30,60]: 270; (60,120]: 159; > 120: 523. **Brak wyraźnego skupienia poniżej 5 min** i tylko 7 identycznych znaczników czasu – Amazon tworzy wysyłki jednego planu jednocześnie, więc czas w arkuszu jest czasem wpisu przez pracownika (jedna wysyłka co 5–30 min). Klastry czasowe są zatem przybliżeniem „sesji roboczej”, a nie odczytem planu z Seller Central.

Wrażliwość na próg (reżim polski, 1640 wysyłek xlsx):

| próg | planów | planów ≥ 2 wysyłek | planów WRO5+XPO1 | śr. wysyłek/plan | max |
|---|---|---|---|---|---|
| 0 min (identyczny czas) | 1633 | 7 | 1 | 1,00 | 2 |
| 5 min | 1615 | 25 | 2 | 1,02 | 2 |
| **10 min** | **1465** | **141** | **39** | **1,12** | **5** |
| 15 min | 1292 | 239 | 82 | 1,27 | 10 |
| 30 min | 977 | 328 | 173 | 1,68 | 12 |
| 60 min | 707 | 363 | 224 | 2,32 | 18 |

### 2.2 Wyniki dla progu 10 min

Wszystkie lata: udział wysyłek należących do planów wieloprzesyłkowych 16,8–27,0 % (2020: 22,4; 2021: 16,8; 2022: 20,8; 2023: 23,3; 2024: 27,0; 2025: 18,4; 2026: 20,3 %); mediana rozpiętości czasu planu wieloprzesyłkowego 7,5–9 min.

Reżim polski (2024-06 … 2026-06, xlsx): **1465 planów / 1640 wysyłek**; rozmiar planu: 1 wysyłka – 1324 (90,4 %), 2 – 112, 3 – 25, 4 – 3, 5 – 1. Planów wieloprzesyłkowych 141 (9,6 % planów, 316 wysyłek = 19,3 % wysyłek).

Skład FC planów wieloprzesyłkowych (141): **jeden FC – 102 (72 %)**: XPO1 61, WRO5 39, HAJ1 1, DTM1 1; **dwa FC (WRO5+XPO1) – 39 (28 %)**. Wśród planów 2-wysyłkowych 27/112 (24 %) jest rozdzielonych, wśród 3-wysyłkowych 9/25 (36 %), 4-wysyłkowych 2/3, 5-wysyłkowych 1/1. Ogółem tylko **2,7 % planów (39/1465) rozdziela się między WRO5 i XPO1**; w 2/3 przypadków wieloprzesyłkowy plan to kilka paczek do tego samego FC (jedna wysyłka = jedna paczka, po 2–3 paczki na sesję).

Plany rozdzielone (39):

* udział sztuk WRO5: średnia 0,695, **mediana 0,74**, p10 0,47, p25 0,51, p75 0,85, p90 0,90, min 0,235, max 0,976; przedziały: (0,1–0,25]: 3, (0,4–0,6]: 9, (0,6–0,75]: 10, (0,75–0,9]: 13, (0,9–1]: 4;
* większa część idzie do WRO5 w 31/39 planów;
* wielkość: łącznie mediana 75 szt. (p25 50, p75 124, max 297); część WRO5 mediana 55 (śr. 70,3), część XPO1 mediana 21 (śr. 22,0, max 70);
* liczba wysyłek: 1 WRO5 + 1 XPO1 w 27 planach, 1+2: 4, 2+1: 5, 1+3: 1, 2+3: 1, 3+1: 1;
* wysyłki w planach rozdzielonych: WRO5 mediana 37 szt. (n 47), XPO1 mediana 14 szt. (n 47) – XPO1 dostaje „resztkę” z długimi produktami.

**Amazon nie dzieli ilości jednego SKU między FC:** na 165 par (plan × fkey) tylko 1 (`adapter|sds_max`, plan 2523) miała ten sam produkt w obu FC. Podział planu jest podziałem po SKU.

### 2.3 Co idzie gdzie – rodziny produktów w planach rozdzielonych i ogółem

| Rodzina | plany rozdzielone: szt. WRO5 / XPO1 (udział WRO5) | reżim polski ogółem (xlsx): szt. WRO5 / XPO1 (udział WRO5) | linii ogółem |
|---|---|---|---|
| auger (świdry) | 325 / 406 (0,44) | 1461 / 19334 (**0,07**) | 1006 |
| adapter | 1100 / 84 (0,93) | 17860 / 2319 (**0,89**) | 779 |
| driver_rod (pobijaki) | 359 / 0 (1,00) | 9068 / 0 (**1,00**) | 410 |
| drill_bit (wiertła) | 5 / 137 (0,04) | 410 / 3477 (**0,11**) | 396 |
| other | 374 / 0 (1,00) | 4463 / 3809 (0,54) | 392 |
| chisel_flat (dłuta) | 50 / 149 (0,25) | 1437 / 2325 (0,38) | 331 |
| set_chisel | 14 / 44 (0,24) | 64 / 877 (0,07) | 140 |
| extension (przedłużki) | 117 / 14 (0,89) | 2044 / 919 (0,69) | 131 |
| driver_pile (wbijaki) | 179 / 0 (1,00) | 3279 / 0 (**1,00**) | 119 |
| chisel_bush (groszkowniki) | 19 / 0 | 728 / 0 (**1,00**) | 97 |
| blade_jigsaw (brzeszczoty) | 85 / 0 | 3239 / 0 (**1,00**) | 77 |
| chisel_gouge | 26 / 4 | 108 / 100 (0,52) | 39 |
| tamper | – | 298 / 0 (1,00) | 38 |
| chisel_spade | – | 918 / 184 (0,83) | 35 |
| chisel_point | – | 36 / 207 (0,15) | 30 |
| blade_recip | 10 / 0 | 280 / 0 (1,00) | 30 |
| spring | 20 / 0 | 209 / 0 (1,00) | 25 |
| grease (smar) | – | 1262 / 0 (1,00) | 22 |
| pin | 20 / 0 | 221 / 0 (1,00) | 16 |
| string, set_adapter, set_drill, saw_disc | – | 100 % WRO5 | 14 / 13 / 9 / 1 |
| handle (gryf) | 0 / 19 | 0 / 57 (0,00) | 3 |

Wzorzec jest niemal deterministyczny na poziomie produktu: **drobne/ciężkie artykuły (adaptery, pobijaki, wbijaki, brzeszczoty, groszkowniki, smar, sprężyny, zawleczki) → WRO5; długie artykuły (świdry, wiertła 600 mm, dłuta 600 mm, zestawy dłut, uchwyty 56 cm) → XPO1**. Wyjątki w rodzinie świdrów są związane z długością: w planach rozdzielonych świdry krótkie (80×250/300/450 mm, 40/60×220 mm) szły do WRO5, a 60/80/100×600 mm do XPO1 (np. plan 3176 z 2026-03-25, plan 3312 z 2026-05-04); `auger|d80|l450` ma 100 % WRO5 (464 szt.), `auger|d80|l600` 1 % WRO5 (575 szt.), `auger|d100|l600` 1 %, `auger|d60|l450` 0 %, `auger|d50|l450` 0 %. Rodzina `other` jest 54/46, bo zbiera i drobiazgi (brzeszczoty 5 szt., młotki gumowe) i szypy 410–460 mm.

Konsekwencja dla narzędzia: prognoza podziału planu to w praktyce **suma per-SKU prawdopodobieństw FC** (a nie proporcja globalna); przy typowym planie „główny produkt + dopełniacze” plan trafia do 2 FC wtedy, gdy miesza się klasy (długie + drobne). W 90 % sesji pracownik i tak tworzy plan jedno-FC.

### 2.4 Plany wieloprzesyłkowe z jednym FC

102 plany: 85 × 2 wysyłki, 16 × 3, 1 × 4; XPO1 61, WRO5 39. Ten sam mechanizm widać też wewnątrz planów rozdzielonych: w planie 3176 (2026-03-25) dwie identyczne paczki po 24 uchwyty 56 cm do XPO1 (`S03607`, `S03608`) obok jednej wysyłki świdrów do WRO5; w planie 3491 (2026-06-30) dwie paczki po 10 zestawów dłut SDS Plus 600 mm do XPO1 (`S03965`, `S03966`). Potwierdza to regułę „jedna wysyłka = jedna paczka”, powtarzaną dla tego samego produktu, gdy ilość przekracza jeden karton.

### 2.5 PDF 2026-07/08 – klastry po numerze dokumentu Apilo

Odstępy numerów `reference_id` między kolejnymi wysyłkami: ≤ 1: 22, 2: 18, 3: 20, (3,5]: 31, (5,10]: 39, (10,20]: 34, (20,50]: 17, (50,100]: 4, (100,300]: 25, > 300: 12. Próg ≤ 10 numerów daje 94 klastry dla 224 wysyłek (54 wieloprzesyłkowe; rozmiary 2: 24, 3: 13, 4: 8, 5: 1, 6: 3, 7: 2, 8: 1, 9: 1, 11: 1); **32 klastry zawierają oba FC** (WRO5 mediana udziału sztuk 0,72, p25 0,42, p75 0,85). Palety pojawiają się w klastrach razem z paczkami (8 klastrów „Paczki+Palety”), np. paleta `PF260704615` (WRO5, 172 szt.) tuż obok palety `PF260704667` (XPO1, 198 szt.) i paczek – czyli jedna sesja może wygenerować paletę na XPO1 i paletę/paczki na WRO5. Wyniki zbieżne z §2.2: rozdzielenie jest częste w sesjach z wieloma wysyłkami, a większość sztuk zostaje na WRO5.

---

## 3. Typowa ilość na linii per produkt – wnioskowanie wielkości kartonu

### 3.1 Rozkład ogólny (reżim polski, 4696 linii)

Ilość na linii: średnia 19,6, p10 5, p25 7, **p50 12**, p75 24, p90 40, p95 56, max 226. Najczęstsze wartości: 10 (781 linii), 5 (503), 20 (424), 30 (222), 3 (210), 15 (196), 7 (192), 14 (168), 2 (131), 9 (130), 6 (128), 50 (127), 12 (110), 4 (110), 11 (78), 13 (70), 18 (69), 40 (68). Podzielne przez 10: 38,2 %; przez 5: 56,5 %; przez 20: 12,7 %; < 5 szt.: 9,8 %.

Po FC: **WRO5** (2442 linii) p50 10, p75 28, p90 50, max 226; podzielne przez 10: 51 %, przez 5: 73 %; top: 10 (486), 5 (337), 20 (308), 30 (137), 3 (114), 50 (109). **XPO1** (2215 linii) p50 12, p75 21, p90 33, max 204; podzielne przez 10 tylko 24 %, przez 5: 38 %; top: 10 (288), **14 (164)**, 5 (158), **7 (139)**, 20 (113), 15 (96), 6 (95), 3 (94), **9 (93)**, 30 (82). Nieokrągłe wielokrotności (7, 9, 11, 13, 14) na XPO1 to pełne kartony świdrów – patrz 3.3.

Po rodzinach (mediana / moda / p75 / % podzielnych przez 10): auger 15 / 10 / 27 / 23 %; adapter 20 / 10 / 30 / 62 %; driver_rod 10 / 5 / 27,5 / 44 %; chisel_flat 9 / 5 / 14 / 19 %; drill_bit 7 / 10 / 10 / 27 %; extension 20 / 34 / 30 / 36 %; blade_jigsaw 20 / 10 / 50 / 82 %; driver_pile 10 / 10 / 30 / 42 %; grease 55 / 100 / 100 / 88 %; set_chisel 6 / 6 / 10 / 24 %; chisel_bush 5 / 5 / 10 / 29 %; tamper 7,5 / 2 / 10; chisel_gouge 5 / 5 / 5,75.

2026-07/08: paczki p50 10 (p75 20, p90 35; podzielne przez 10: 46 %), palety p50 21 (p25 14, p75 38, p90 50; podzielne przez 10: 30 %; top 14 ×16, 30 ×13, 10 ×8, 21 ×8, 39 ×6).

### 3.2 Tabela top-60 produktów (reżim polski, wg sztuk) – ilość na linii i wnioskowany moduł

Kolumny: linie / szt. / udział WRO5 / mediana / moda (liczba linii) / najczęstsze wartości / **wnioskowany moduł kartonu** (wartość, przez którą dzieli się ≥ 60–100 % linii i która sama występuje jako ilość) / % linii solo (jedyny produkt w wysyłce).

| # | fkey (przykład nazwy) | linie | szt. | WRO5 | med. | moda | najczęstsze ilości | **moduł** | solo |
|---|---|---|---|---|---|---|---|---|---|
| 1 | adapter\|sds_max (klucz zbiorczy: adapter SDS Max, przedłużenie 1000 SDS Max…) | 243 | 5029 | 0,65 | 20 | 10 (71) | 10×71, 20×37, 35×21, 30×17, 21×13, 9×12 | 5 (74 %), 10 (59 %) | 40 % |
| 2 | other (klucz zbiorczy: słupek 1000 mm, brzeszczoty 5 szt., …) | 210 | 4209 | 0,58 | 15 | 10 (34) | 10×34, 20×32, 30×22, 15×21, 24×15 | 5 (70 %) | 13 % |
| 3 | adapter\|sds_plus (4APlus) | 76 | 3693 | 1,00 | 40 | 20 (17) | 20×17, 50×10, 60×8, 30×8, 10×6, 70×5, 170×4 | **10 (91 %)**; typ. 20–60 | 8 % |
| 4 | adapter\|m14 (4AM14) | 108 | 3325 | 1,00 | 15 | 10 (21) | 10×21, 5×14, 50×14, 40×10, 20×8 | 5 (88 %), 10 (66 %); dwa tryby 5–10 i 40–50 | 3 % |
| 5 | adapter\|m14\|unf_1_2 (4A1/2-20UNF-M14) | 47 | 2970 | 1,00 | 50 | 50 (13) | 50×13, 30×11, 100×5, 40×4, 70×3, 150×3 | **10 (91 %)**; typ. 50 | 0 % |
| 6 | other\|sds_plus (klucz zbiorczy: gwoździarki 6PO..pk, wiertła uziemiające) | 87 | 2607 | 0,40 | 26 | 10 (15) | 10×15, 26×10, 50×8, 39×8, 20×7 | 5 (61 %); część 13 (26, 39) | 1 % |
| 7 | auger\|d80\|sds_plus (świder 80 SDS Plus) | 51 | 2571 | 0,00 | 33 | 33 (17) | 33×17, 11×11, 66×6, 22×3, 132×3 | **11 (84 %)**; typ. linia 33 = 3 kartony | 4 % |
| 8 | blade_jigsaw\|T744D\|l180\|n5 (5 brzeszczotów T744D) | 30 | 2481 | 1,00 | 50 | 50 (8) | 50×8, 20×4, 150×3, 30×3, 220×3 | 10 (87 %); typ. 50, duże 150–220 | 13 % |
| 9 | driver_pile\|d20.2\|l28\|sds_plus (wbijak 20,2×28) | 24 | 1958 | 1,00 | 85 | 120 (5) | 120×5, 125×3, 100×2, 40×2, 70×2 | 5 (96 %); typ. 100–125 | 38 % |
| 10 | auger\|sds_plus (klucz zbiorczy PDF: 1ZWG..dp) | 58 | 1846 | 0,00 | 27 | 14 (7) | 14×7, 27×5, 9×4, 45×4, 39×4, 21×4 | zależny od średnicy (7/9/11/13/15) | 2 % |
| 11 | driver_rod\|d20.2\|l165\|sds_max (gwoździowkrętak 20,2) | 35 | 1721 | 1,00 | 56 | 56 (12) | 56×12, 58×6, 60×5, 30×2 | **stała partia 56–60** (74 % solo) | 74 % |
| 12 | driver_rod\|d13.5\|l34\|sds_plus (wbijak 13,5×34×223) | 19 | 1520 | 1,00 | 80 | 100 (5) | 100×5, 50×3, 80×2, 30×2, 170, 190 | 10 (89 %); typ. 50–100 | 11 % |
| 13 | grease\|d100 (smar MoS2 100 ml) | 24 | 1462 | 1,00 | 55 | 100 (10) | 100×10, 30×3, 20×2, 25×2, 40×2 | **100** (20: 88 %) | 42 % |
| 14 | adapter\|unc_1_1_4 (4A1.1/4-1/2, -WG) | 73 | 1456 | 1,00 | 20 | 20 (17) | 20×17, 10×12, 15×8, 5×6, 30×5 | 5 (78 %); typ. 10–20 | 15 % |
| 15 | extension\|l400 (przedłużka świdra 400 mm, 5PR400) | 41 | 1378 | 1,00 | 34 | 34 (37) | 34×37, 30×2, 20, 40 | **34 (90 %)** – stały karton | 95 % |
| 16 | adapter (klucz zbiorczy: Stihl, Makita, …) | 71 | 1263 | 1,00 | 18 | 10 (15) | 10×15, 20×14, 30×10, 5×9, 15×5 | 5 (86 %) | 4 % |
| 17 | auger\|d150\|sds_plus | 41 | 1255 | 0,00 | 28 | 28 (9) | 28×9, 35×6, 14×5, 21×5, 7×4, 42×3 | **7 (95 %)**; typ. 14–35 | 2 % |
| 18 | chisel_spade\|d75\|l410\|hex30 (szpadel 75×410 HEX30) | 35 | 1102 | 0,83 | 11 | 10 (15) | 10×15, 11×10, 70×6, 100 | 10 (69 %); małe 10–11 lub 70–100 | 74 % |
| 19 | auger\|d60\|l800\|sds_plus | 13 | 887 | 0,00 | 39 | 39 (6) | 39×6, 117×2, 78×2, 26, 156, 81 | **13** (39 = 3 kartony; 85 % podz. przez 39) | 0 % |
| 20 | auger\|d50\|l800\|sds_plus | 34 | 875 | 0,00 | 28 | 14 (15) | 14×15, 42×11, 28×7, 7 | **14 (97 %)** (7 = pół) | 21 % |
| 21 | auger\|d60\|l600 (świder ogrodowy 60×600, 1Wo60x600) | 40 | 874 | 0,00 | 25,5 | 26 (14) | 26×14, 25×5, 27×4, 7×3 | **13** (26 = 2 kartony) | 60 % |
| 22 | adapter\|hex (4AHex) | 26 | 866 | 1,00 | 30 | 50 (7) | 50×7, 30×7, 20×3, 10×2 | 10 (81 %); typ. 30–50 | 4 % |
| 23 | driver_rod\|d16.5\|l34\|sds_plus | 18 | 860 | 1,00 | 50 | 50 (3) | 50×3, 40×3, 20×2, 70×2, 55×2, 60×2 | 5 (100 %), 10 (78 %); typ. 40–60 | 0 % |
| 24 | adapter\|m18\|unc_1_1_4 (4AM18-1.1/4) | 49 | 829 | 1,00 | 20 | 20 (10) | 20×10, 10×8, 28×7, 5×5, 12×4, 27×3 | 10 (53 %) lub 28 (karton 28?) | 29 % |
| 25 | auger\|d40\|sds_plus | 25 | 817 | 0,00 | 30 | 45 (9) | 45×9, 15×8, 30×5 | **15 (92 %)** | 4 % |
| 26 | auger\|d150\|sds_plus\|dbl | 33 | 766 | 0,00 | 21 | 14 (7) | 14×7, 7×6, 21×5, 35×5, 28×4, 42×2 | **7 (94 %)** | 3 % |
| 27 | chisel_flat\|d75\|l600\|sds_max (dłuto 75×600 SDS Max, 3DB75x600m) | 52 | 728 | 0,00 | 14 | 14 (36) | 14×36, 16×4, 10×3, 8×2 | **14 (69 % linii = 14)** | 85 % |
| 28 | auger\|d100\|sds_plus | 46 | 726 | 0,00 | 10 | 10 (22) | 10×22, 20×16, 40×2, 30×2 | **10 (91 %)** | 4 % |
| 29 | chisel_flat\|d75\|l410\|hex30 (3DB75x410h30) | 11 | 660 | 1,00 | 50 | 10 (5) | 10×5, 50×3, 140×2, 180 | 10 (100 %); na paletach 50 | 45 % |
| 30 | auger\|d100\|l600 (1Wo100x600) | 36 | 645 | 0,01 | 19 | 20 (15) | 20×15, 19×9, 10×3, 5×2 | **20** (19 = karton niepełny) | 75 % |
| 31 | auger\|d120\|sds_plus | 31 | 639 | 0,00 | 18 | 9 (15) | 9×15, 18×5, 27×4, 36×4, 54, 63 | **9 (100 %)** | 0 % |
| 32 | auger\|d50\|l450 (1Wo50x450) | 24 | 635 | 0,00 | 27 | 30 (5) | 30×5, 50×4, 15×2, 20×2 | 5 (62 %); typ. 15–50 | 8 % |
| 33 | auger\|sds_max (klucz zbiorczy PDF: 1ZWG..dm) | 29 | 610 | 0,00 | 18 | 14 (6) | 14×6, 30×5, 10×4, 21×3, 39×2 | zależny od średnicy | 0 % |
| 34 | auger (klucz zbiorczy PDF: 1WG..d) | 30 | 593 | 0,00 | 14,5 | 14 (5) | 14×5, 6×3, 18×3, 36×2 | zależny od średnicy | 13 % |
| 35 | auger\|d150\|sds_max | 37 | 593 | 0,00 | 14 | 7 (13) | 7×13, 14×9, 28×5, 21×5, 35×2 | **7 (95 %)** | 0 % |
| 36 | auger\|d80\|l600 (1Wo80x600) | 31 | 575 | 0,01 | 20 | 24 (11) | 24×11, 20×7, 5×3, 10×3 | **24** (lub 12) | 55 % |
| 37 | driver_rod\|d13.5\|l34\|sds_max | 13 | 568 | 1,00 | 45 | 70 (3) | 70×3, 50×2, 40×2, 20×2 | 5 (92 %), 10 (77 %); typ. 40–70 | 23 % |
| 38 | chisel_flat\|d135\|l410\|hex30 (szypa 135×410 HEX30) | 26 | 557 | 0,00 | 29 | 29 (12) | 29×12, 5×6, 50, 14, 58, 28 | **29** (58 = 2 kartony) | 27 % |
| 39 | driver_rod\|d13.5\|sds_plus (pobijak 13,5 SDS Plus, 6PO13,5p) | 7 | 550 | 1,00 | 50 | 50 (2) | 50×2, 20, 150, 160, 30, 90 | 10 (100 %); partie 50–160 | 29 % |
| 40 | other\|sds_max (klucz zbiorczy: szypa 110 SDS Max, młotek gumowy…) | 50 | 545 | 0,23 | 10 | 10 (11) | 10×11, 5×10, 13×8, 2×4 | 5; szypa 110: 29 na palecie | 14 % |
| 41 | set_chisel\|sds_plus\|n3 (zestaw dłut SDS Plus 600, 3 szt.) | 53 | 543 | 0,06 | 10 | 10 (32) | 10×32, 15×11, 8×3 | **10 (60 %)**, 5 (85 %) | 74 % |
| 42 | auger\|d40 | 29 | 538 | 0,15 | 15 | 15 (8) | 15×8, 16×4, 12×3, 32×2 | 15 (niepewny) | 17 % |
| 43 | other\|unc_1_1_4 (przedłużka 1 1/4 UNC do wierteł diamentowych) | 22 | 528 | 1,00 | 12 | 12 (14) | 12×14, 94, 60, 7, 5, 40 | **12 (64 % linii)** | 64 % |
| 44 | auger\|d80 | 39 | 517 | 0,17 | 11 | 11 (10) | 11×10, 12×6, 22×5, 5×5, 10×3, 33×2 | **11** (44 %) | 8 % |
| 45 | auger\|d120\|sds_max | 29 | 495 | 0,00 | 18 | 18 (14) | 18×14, 9×9, 27×6 | **9 (100 %)** | 0 % |
| 46 | auger\|d40\|l450 (1Wo40x450) | 18 | 491 | 0,01 | 25 | 20 (3) | 20×3, 10×2, 50×2, 30×2, 40×2 | 10 (67 %) | 11 % |
| 47 | auger\|d60 | 32 | 489 | 0,12 | 13 | 12 (7) | 12×7, 13×6, 14×5, 26×2, 7×2 | 12–14 (niepewny; prawdop. 13) | 16 % |
| 48 | auger\|d150 | 38 | 483 | 0,00 | 14 | 7 (17) | 7×17, 14×14, 21×5, 35, 28 | **7 (100 %)** | 0 % |
| 49 | auger\|d80\|l450 | 22 | 464 | **1,00** | 20 | 30 (6) | 30×6, 10×3, 20×3, 8×2, 31×2, 32×2 | 10 (55 %) | 45 % |
| 50 | driver_rod\|d20.2\|sds_plus | 4 | 460 | 1,00 | 125 | 130 (2) | 130×2, 80, 120 | 10; partie 80–130 | 50 % |
| 51 | blade_jigsaw\|T744D (nożyki T744D, 7NT744D) | 3 | 450 | 1,00 | 150 | – | 200, 150, 100 | 50; partie 100–200 | 33 % |
| 52 | auger\|d60\|l450 (1Wo60x450) | 19 | 447 | 0,00 | 30 | 30 (9) | 30×9, 20×4, 35×2, 5×2 | 5 (95 %), 10 (74 %); typ. 30 | 53 % |
| 53 | driver_rod\|d13.5\|l35\|sds_max (6PO13,5mP) | 31 | 439 | 1,00 | 10 | 10 (15) | 10×15, 20×4, 5×3, 15×2 | 5 (84 %), 10 (65 %) | 13 % |
| 54 | extension\|l120\|m14 (5PRM14x120) | 22 | 430 | 1,00 | 20 | 20 (7) | 20×7, 10×6, 30×5, 25 | 10 (82 %) | 0 % |
| 55 | other\|d36\|sds_plus (młotek gumowy SDS Plus 36 mm) | 19 | 425 | 1,00 | 20 | 10 (7) | 10×7, 20×3, 50×3, 30×3, 25×2 | 5 (100 %), 10 (84 %) | 0 % |
| 56 | driver_rod\|d13.5\|l100\|sds_plus | 3 | 420 | 1,00 | 160 | 160 (2) | 160×2, 100 | 20; partie 100–160 | 67 % |
| 57 | auger\|d100\|sds_max\|dbl | 26 | 420 | 0,00 | 10 | 10 (15) | 10×15, 20×8, 30×2, 50 | **10 (100 %)** | 0 % |
| 58 | driver_pile\|d16.5\|l25\|sds_max | 15 | 417 | 1,00 | 20 | 20 (4) | 20×4, 10×3, 50×2, 30×2, 70 | 10 (87 %) | 7 % |
| 59 | auger\|d60\|sds_max | 21 | 402 | 0,00 | 12 | 12 (12) | 12×12, 36×5, 24×3, 6 | **12 (95 %)** | 14 % |
| 60 | extension\|l750\|sds_max (5PR750m-m) | 28 | 395 | 0,00 | 14 | 14 (22) | 14×22, 15×5, 12 | **14 (79 % linii)** | 71 % |

### 3.3 Moduły kartonowe wg wymiaru (agregacja niezależna od fkey, reżim polski)

**Świdry (auger) wg średnicy** – ilość na linii: % linii podzielnych przez moduł:

| Ø [mm] | linie | szt. | najczęstsze ilości | **moduł kartonu** | udział podzielnych |
|---|---|---|---|---|---|
| 40 | 94 | 2236 | 15×23, 45×11, 30×9, 12×6, 10×6 | **15** (SDS: 72 %); 40D/40D SDS Max w PDF także 39 = 3×13 | 48 % (15) |
| 50 | 103 | 2180 | 14×18, 13×14, 15×13, 42×11, 20×9, 28×7 | **14** (ogrodowe 450/800: 40 %; 1ZWG50dp: 42, 84) | 35 % (14), 39 % (7) |
| 60 | 142 | 3371 | 12×22, 26×17, 13×15, 30×9, 39×7, 36×7 | **13** (SDS Plus/ogrodowe: 26, 39, 65, 78); **12** dla SDS Max (12, 24, 36) | 31 % (13) |
| 80 | 166 | 4393 | 11×31, 33×21, 5×13, 10×12, 24×11, 20×10 | **11** (SDS: 82 %; 11, 22, 33, 66, 132); ogrodowe 80×600: 24; 80×450: 30/10 | 43 % (11) |
| 100 | 169 | 2659 | 20×56, 10×50, 5×13, 19×9, 30×7 | **10** (SDS: 95 %); ogrodowe 100×600: 20 (19) | 69 % (10) |
| 120 | 117 | 1948 | 9×54, 18×35, 27×14, 36×7, 54 | **9** | 97 % (9) |
| 150 | 172 | 3449 | 7×47, 14×43, 21×23, 28×21, 35×14, 42×6, 70×4 | **7** | 95 % (7) |
| 200 | 15 | 126 | 6×9, 12×6 | **6** | 100 % (6) |

Wniosek: liczba świdrów w kartonie maleje ze średnicą (15 → 14 → 13 → 11 → 10 → 9 → 7 → 6) i **linie na paletach są wielokrotnościami tych kartonów** (§5: 1ZWG150dm 7/14/21/49, 1ZWG120dm 9/18/27, 1ZWG60dp 39/65/78, 1ZWG80dp 22/33, 1WG200h 6/18).

**Przedłużki (extension):** 400 mm (świder) – **34** (37/41 linii); 750 SDS Max – **14** (22/28); 1180 SDS Max – **9** (10/10); 1000 SDS Max – 10 (9/16; też 50, 60); 1000 (świder, 5PR1000) – 30 (8/12; 16, 46); 600 (świder) – 24 (4/4); 800 – 20 (3/3); 5000 mm – 4 (5/5, tylko na paletach); 120 i 250 M14 – 10/20; 200 mm 1 1/4 UNC – 12 (11).

**Dłuta (chisel_flat):** 75×600 SDS Max – **14** (36/52); 110×410 SDS Max – **7** (16/23); 135×410 HEX30 (szypa) – **29** (12/26); 30×410 hex – 14/13 (13+7 z 28); 75×400 HEX28 – 9/10 (11+9 z 24); 75×410 HEX30 – 10 (paczki) / 50 (palety); 50×600 SDS Max – 10/18/16 (mieszane).

**Wiertła (drill_bit):** 40×600 SDS Max – **7** (26/39); 40×600 SDS Plus – 7 (12/32; też 6, 18, 24); pozostałe wiertła 10–32 mm – 5/10 (mediana 5–10 szt., dużo drobnych ilości 2–5).

**Pobijaki (driver_rod):** 13,5 SDS Plus – 100 (50–190; 93 % podz. przez 10); 16,5 SDS Plus – 40–60; 20,2 SDS Max ×165 – 56–60 (stała partia); 20,2 SDS Plus – 80–130; 13,5 SDS Max – 10/20; 25,5 i 32,5 (SDS Plus/Max) – 10/20; warianty HEX28/HEX30 – 2–5 szt. (drobne dopełnienia).

**Wbijaki (driver_pile):** 20,2×28 SDS Plus – 100–125 (75 % podz. przez 10); 16,5×25 SDS Max – 10/20; 85×105 SDS Max – 7 (11/30; palety 48, 60); 85×105 HEX30 – 5–6 (palety 40, 52); 55 SDS Max – 5/10.

**Adaptery:** wszystkie warianty moduł 5/10 (52–91 % podzielnych przez 10); typowe partie: SDS Plus 20–60, M14 10 lub 40–50, 1/2-20UNF-M14 50, HEX 30–50, 1 1/4 UNC 10–20, M18-1 1/4 20 (28). **Brzeszczoty:** T744D 5 szt. – 50 (10; 87 %); T744D luzem – 100–200. **Smar 100 ml – 100.** **Zestawy dłut** – 10 (SDS Plus 600 n3), 4–6 (HEX 410). **Gryf (uchwyt T 56 cm)** – 19–20.

---

## 4. Liczba produktów na wysyłkę; produkty „solo” vs „w miksie”

### 4.1 Liczba odrębnych produktów (fkey) i rodzin – reżim polski

| n fkey | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8+ | razem |
|---|---|---|---|---|---|---|---|---|---|
| WRO5 | 384 (43 %) | 142 | 115 | 98 | 71 | 40 | 22 | 18 | 890 |
| XPO1 | 598 (62 %) | 105 | 63 | 65 | 47 | 26 | 18 | 36 | 958 |

Liczba rodzin: XPO1 – 1 rodzina w 745/958 (78 %), 2: 144, 3: 54, 4: 13, 5: 2; WRO5 – 1 rodzina 478/890 (54 %), 2: 180, 3: 125, 4: 68, 5: 29, 6: 10. Wśród wysyłek wieloproduktowych jedną rodzinę ma 41 % na XPO1 (śr. 1,83 rodziny) i 19 % na WRO5 (śr. 2,59) – **palety XPO1 to niemal wyłącznie świdry, paczki WRO5 to miks rodzin drobnych.**

Mediana sztuk wg liczby produktów: 1 → 14; 2 → 39; 3 → 50; 4 → 70; 5 → 87; 6 → 92; 7 → 118; 8+ → 160,5. Ilość na linii jest nieco większa gdy produkt jedzie solo (p50 14, p75 25) niż w miksie (p50 10, p75 21).

### 4.2 Rodziny – udział linii „solo” (jedyny produkt w wysyłce) i średnia liczba współpasażerów

| Rodzina | linie | szt. | % linii solo | śr. innych produktów w wysyłce |
|---|---|---|---|---|
| handle (gryf) | 8 | 151 | 88 % | 0,1 |
| chisel_spade | 35 | 1102 | 74 % | 1,1 |
| set_chisel | 160 | 1086 | 71 % | 0,6 |
| extension | 190 | 4036 | 55 % | 1,6 |
| tamper | 38 | 298 | 47 % | 2,0 |
| grease | 24 | 1462 | 42 % | 2,9 |
| chisel_flat | 364 | 4150 | 40 % | 2,2 |
| driver_pile | 140 | 3625 | 33 % | 1,9 |
| chisel_point | 37 | 297 | 30 % | 2,4 |
| drill_bit | 442 | 4136 | 18 % | 2,9 |
| adapter | 866 | 22394 | 16 % | 3,1 |
| other | 420 | 8575 | 16 % | 4,3 |
| driver_rod | 463 | 10460 | 15 % | 2,7 |
| auger | 1127 | 23854 | 14 % | 4,1 |
| blade_jigsaw | 100 | 3999 | 5 % | 4,4 |
| spring | 26 | 212 | 4 % | 3,6 |
| chisel_bush | 115 | 894 | 2 % | 4,2 |
| blade_recip / pin / chisel_gouge / set_adapter / string / set_drill / saw_disc | 31 / 20 / 42 / 17 / 15 / 14 / 2 | – | 0 % | 3,0–5,1 |

### 4.3 Produkty typowo wysyłane solo (≥ 10 linii) – kandydaci na „produkt główny” paczki

extension|l1180|sds_max 100 % (10 linii, 9 szt./linię); extension|l400 95 % (34 szt.); set_chisel|hex30|n3 90 %; chisel_flat|d75|l600|sds_max 85 % (14 szt.); chisel_flat|d75|l400|hex28 83 %; chisel_flat|d110|l410|sds_max 83 %; other|hex30 82 %; auger|d100|l600 75 % (20 szt.); driver_rod|d20.2|l165|sds_max 74 % (56 szt.); set_chisel|sds_plus|n3 74 % (10 szt.); chisel_spade|d75|l410|hex30 74 %; set_chisel|hex|n50 74 %; extension|l750|sds_max 71 % (14 szt.); chisel_flat|d30|l410|hex 71 %; extension|l1000|sds_max 69 %; drill_bit|d40|l600|sds_max 67 % (7 szt.); driver_rod|d20.2|sds_max 64 %; other|unc_1_1_4 64 % (12 szt.); set_chisel|sds_max|n50 62 %; auger|d60|l600 60 % (26 szt.); drill_bit|d40|l600|sds_plus 56 %; auger|d80|l600 55 % (24 szt.); auger|d60|l450 53 % (30 szt.).

Wzorzec: produkt solo = **jeden pełny karton producenta wysłany jako jedna paczka FBA** (34 przedłużek, 14 dłut, 26 świdrów, 56 pobijaków, 10 zestawów).

### 4.4 Produkty nigdy niewysyłane solo (0 % z ≥ 10 linii) – naturalne „dopełniacze”

adapter|m14|unf_1_2 (47 linii, 2970 szt.), auger|d120|sds_plus (31), driver_rod|d16.5|l34|sds_plus (18), auger|d60|l800|sds_plus (13), auger|d120|sds_max (29), auger|d150 (38), driver_rod|d32.5|l45|sds_plus (20), adapter|sds_plus|m14 (30), other|d36|sds_plus (19), extension|l120|m14 (22), auger|d100|sds_max|dbl (26), adapter|hex|unc_1_1_4 (25), auger|d150|sds_max (37), auger|sds_max (29), drill_bit|d16|l600|sds_plus (12), chisel_flat|d30|l250|sds_plus (10), drill_bit|d10|l600|sds_plus (17), chisel_point|l600|sds_plus (15), auger|d50 (11), auger|d80|hex (15; śr. 7,6 współpasażerów), chisel_bush|d140|sds_plus (13), auger|d120 (15), pin|n5 (14), blade_jigsaw|T744D|l180 (10), auger|d150|sds_max|dbl (20). Wszystkie świdry SDS Ø 100–150 są wyłącznie składnikami palet.

### 4.5 Najczęstsze pary rodzin w jednej wysyłce (liczba wysyłek, reżim polski)

Ogółem: adapter+driver_rod 141, adapter+other 122, auger+other 90, adapter+blade_jigsaw 55, driver_rod+other 55, adapter+auger 53, adapter+chisel_flat 51, adapter+chisel_bush 44, driver_pile+driver_rod 42, chisel_flat+drill_bit 40, adapter+extension 39, chisel_flat+other 39, auger+chisel_flat 39, chisel_flat+driver_rod 36, auger+extension 30, auger+drill_bit 29.
WRO5: adapter+driver_rod 140, adapter+other 96, driver_rod+other 55, adapter+blade_jigsaw 53, adapter+chisel_flat 46, adapter+chisel_bush 44, driver_pile+driver_rod 42, chisel_flat+driver_rod 36, adapter+extension 32, chisel_bush+driver_rod 28.
XPO1: auger+other 84, adapter+auger 35, chisel_flat+drill_bit 33, auger+chisel_flat 31, auger+drill_bit 26, adapter+other 25, auger+extension 25, drill_bit+set_chisel 19, chisel_flat+other 18, chisel_flat+set_chisel 18.

---

## 5. Palety vs paczki – 2026-07/08 linia po linii

### 5.1 Wszystkie 22 palety

Format linii: nazwa (SKU Apilo) × ilość.

**2026-07 (11 palet, 1655 szt.)**

1. `PF260706014` **XPO1**, 5 linii, 109 szt.: Świder 100D SDS Max (1ZWG100dm) ×30; Świder 150D SDS Max (1ZWG150dm) ×14; Świder 150H SDS Plus (1ZWG150hp) ×14; Świder 200D (1WG200d) ×12; Świder 40D SDS Max (1ZWG40dm) ×39.
2. `PF260705735` **XPO1**, 6 linii, 121 szt.: Przedłużka do świdra 5000 mm ×4; Świder 100D SDS Max ×10; Świder 100D SDS Plus (1ZWG100dp) ×50; Świder 120D (1WG120d) ×36; Świder 150D SDS Plus (1ZWG150dp) ×14; Świder 150H SDS Plus ×7.
3. `PF260705416` **XPO1**, 7 linii, 164 szt.: Przedłużka 5000 mm ×4; Świder 150D SDS Plus ×14; Świder 150H (1WG150h) ×7; Świder 60D (1WG60d) ×14; Świder 60D SDS Plus (1ZWG60dp) ×65; Świder 80D SDS Max (1ZWG80dm) ×10; Świder 80D SDS Plus (1ZWG80dp) ×50.
4. `PF260704667` **XPO1**, 7 linii, 198 szt.: Przedłużka 5000 mm ×4; Świder 150D SDS Max ×14; Świder 40D SDS Max ×39; Świder 50D SDS Max (1ZWG50dm) ×12; Świder 50D SDS Plus (1ZWG50dp) ×84; Świder 80D (1WG80d) ×33; Wiertło do gleby 50D Hex ×12.
5. `PF260704615` **WRO5**, 5 linii, 172 szt.: Pobijak 50 mm HEX30 (6PO50x220h30) ×20; Przedłużka do świdra 400 mm (5PR400) ×40; Wbijak do pali 85×105×234 SDS Max (6PO85x234m) ×60; Wbijak do pali 65×80×235 HEX30 (6PO65x235h30) ×12; Wbijak do pali 85×105×234 HEX30 (6PO85x234h30) ×40.
6. `PF260704045` **XPO1**, 7 linii, 171 szt.: Przedłużka do świdra 1000 mm (5PR1000) ×16; Świder 100D (1WG100d) ×40; Świder 100H SDS Plus ×30; Świder 150H SDS Plus ×14; Świder 40D SDS Plus (1ZWG40dp) ×39; Świder 80D SDS Max ×10; Świder 80D SDS Plus ×22.
7. `PF260703084` **XPO1**, 7 linii, 178 szt.: Przedłużka 1000 mm ×30; Świder 120D SDS Plus (1ZWG120dp) ×36; Świder 150D SDS Max ×14; Świder 200H (1WG200h) ×6; Świder 40D (1WG40d) ×30; Świder 40D SDS Plus ×60; Świder 80D SDS Plus ×2.
8. `PF260702302` **XPO1**, 5 linii, 186 szt.: Przedłużka 1000 mm ×30; Świder 100H SDS Plus ×10; Świder 150D SDS Max ×21; Świder 200H ×6; Świder 60D SDS Plus ×119.
9. `PF260700192` **XPO1**, 6 linii, 138 szt.: Przedłużka 1000 mm ×46; Świder 100D SDS Plus ×20; Świder 100H SDS Plus ×30; Świder 150D SDS Plus ×22; Świder 150H SDS Plus ×14; Świder 200D ×6.
10. `PF260700021` **XPO1**, 5 linii, 138 szt.: Świder 100H SDS Max ×30; Świder 120D ×18; Świder 150D SDS Max ×21; Świder 60D SDS Plus ×39; Świder 80D SDS Max ×30.
11. `PF260700017` **XPO1**, 4 linie, 80 szt.: Świder 100D ×10; Świder 150D (1WG150d) ×35; Świder 150H ×21; Świder 150H SDS Plus ×14.

**2026-08 (11 palet, 1645 szt.)**

12. `PF260806243` **WRO5**, 4 linie, 170 szt.: Dłuto do betonu 75×410 HEX30 (3DB75x410h30) ×50; Pobijak SDS Max 50×70×220 (6PO50x220m) ×20; Wbijak do pali 85×105×234 SDS Max ×48; Wbijak do pali 85×105×234 HEX30 ×52.
13. `PF260805601` **XPO1**, 6 linii, 137 szt.: Przedłużka 1000 mm ×16; Świder 100D ×10; Świder 150D SDS Plus ×14; Świder 150H SDS Max ×28; Świder 60D SDS Max (1ZWG60Dm) ×36; Świder 80D SDS Plus ×33.
14. `PF260805112` **XPO1**, 6 linii, 174 szt.: Świder 100H SDS Max ×10; Świder 150D SDS Plus ×21; Świder 50D SDS Plus ×42; Świder 60D SDS Plus ×39; Świder 80D SDS Plus ×33; Szypa SDS Max 110×460 (3S110m) ×29.
15. `PF260804227` **XPO1**, 6 linii, 128 szt.: Przedłużka 5000 mm ×4; Świder 120D SDS Max (1ZWG120dm) ×27; Świder 150D SDS Max ×14; Świder 150H SDS Max ×14; Świder 60D SDS Plus ×39; Świder 80D SDS Max ×30.
16. `PF260803393` **XPO1**, 6 linii, 129 szt.: Przedłużka 5000 mm ×4; Świder 120D SDS Max ×18; Świder 150H ×14; Świder 150H SDS Plus ×21; Świder 60D ×42; Świder 80D SDS Max ×30.
17. `PF260802745` **XPO1**, 3 linie, 159 szt.: Przedłużka 1000 mm ×20; Świder 150D SDS Max ×49; Świder 40D SDS Plus ×90.
18. `PF260802470` **XPO1**, 6 linii, 205 szt.: Przedłużka 1000 mm ×30; Świder 100D SDS Plus ×42; Świder 100H SDS Plus ×50; Świder 120D SDS Max ×9; Świder 40D ×45; Szypa HEX30 135×410 (3S135h30) ×29.
19. `PF260802126` **WRO5**, 4 linie, 125 szt.: Dłuto 75×410 HEX30 ×50; Ubijaczka srebrna HEX30 150×150 (6U8,6h30) ×25; Ubijaczka czarna HEX30 250×200 (6U6,6h30) ×10; Wbijak do pali 50×70×220 HEX30 (6PO50x220h30) ×40.
20. `PF260801816` **XPO1**, 6 linii, 106 szt.: Świder 120D SDS Max ×9; Świder 150D SDS Max ×21; Świder 150H ×14; Świder 150H SDS Plus ×21; Świder 60D ×28; Świder 60D HEX ×13.
21. `PF260801028` **XPO1**, 6 linii, 210 szt.: Przedłużka 1000 mm ×30; Świder 120D ×36; Świder 150D SDS Max ×7; Świder 40D SDS Plus ×45; Świder 60D SDS Plus ×78; Świder 80D SDS Max ×14.
22. `PF260800246` **XPO1**, 5 linii, 102 szt.: Świder 120D ×18; Świder 150H SDS Plus ×21; Świder 200H ×18; Świder 40D ×30; Świder 40D SDS Plus ×15.

### 5.2 Podsumowanie palet

* Sztuki wg rodzin: **auger 2537 (77 %)**, extension 278 (przedłużka 1000 mm 218, 5000 mm 20, 400 mm 40), driver_pile 252, chisel_flat 100, other 93 (szypy 58, ubijaczki 35), driver_rod 40. Na XPO1: auger 2537 + extension 238 + szypy 58 = 2833; na WRO5: driver_pile 252 + chisel_flat 100 + extension 40 + driver_rod 40 + ubijaczki 35 = 467.
* Paleta XPO1 = **4–7 linii świdrów SDS Plus/SDS Max/plain o różnych średnicach (40–200 mm) + zwykle jedna linia przedłużki 1000 mm (16–46 szt.) lub 5000 mm (4 szt.)**, czasem szypa (29). Mediana 138 szt.
* Paleta WRO5 (3 szt.) = wbijaki do pali 85×105 (40–60 szt.), pobijaki 50 mm (20), dłuto 75×410 HEX30 (50), przedłużka 400 mm (40), ubijaczki; 125–172 szt.
* Ilość na linii palety: mediana 21 (p25 14, p75 38, max 119) – linie są wielokrotnościami kartonów z §3.3.
* Produkty z palet (16 fkey) vs z paczek (157 fkey): część wspólna tylko 8; **wyłącznie na paletach**: auger|sds_max, auger|hex, extension|l1000, extension|l5000, chisel_flat|d75|l410|hex30, driver_pile|d85|l105|sds_max, driver_pile|d65|l80|hex30, driver_rod|d50|hex30. Udział palet w sztukach rodziny: auger 84 %, driver_pile 78 %, extension 32 %.
* W danych xlsx (2024-06 … 2026-06) proxy palety = wysyłka XPO1 ≥ 100 szt.: 123 wysyłek, mediana 159 szt., 6 linii, 6 produktów; skład: auger 13567 szt. (68 %), other 3023, adapter 1503, chisel_flat 631, extension 520, drill_bit 436; kombinacje rodzin: auger+other 38, tylko auger 27, adapter+auger+other 16, auger+chisel_flat 7. Miesięcznie 1–14 takich wysyłek (2026-03 i 2026-04 po 14). Historycznie palety zawierały więc więcej dodatków (adaptery, dłuta, wiertła) niż w VII–VIII 2026, gdzie są niemal czysto świdrowe.

### 5.3 Paczki 2026-07/08 (198)

* 1 produkt w 134/198 (68 %): WRO5 53/102, XPO1 81/96 (84 %); ≥ 4 produktów: WRO5 24, XPO1 7.
* **XPO1 (96 paczek, 1426 szt., mediana 14 szt.)**: świdry ogrodowe 1Wo (60×600 ×26 – 5 paczek, 50×450, 40×450, 100×600, 80×600), przedłużki świdrów 600 (24), 800 (20), SDS Max 750 (15), 1000 (10), 1180 (9), wiertła 40×600 i 32×600 SDS Plus (4–11), zestawy dłut SDS Plus 600 (10), zestawy HEX 410 (4–7), dłuta 75×600 SDS Max (14), gryf 56 cm (20), szypy (5). Rodziny: auger 428, extension 311, drill_bit 225, chisel_flat 170, handle 94, set_chisel 83, other 61, chisel_point 54.
* **WRO5 (102 paczki, 5248 szt., mediana 40 szt.)**: pobijaki 13,5 SDS Plus (6 paczek, 530 szt.: 30–160), nożyki T744D (100–200), adaptery SDS Plus/SDS Max/M14/HEX/M18 (10–100), smar (100), pobijaki 20,2 SDS Max (50), przedłużki 400 mm (34), 200 mm (30), groszkowniki (10–25), zestawy adapterów (10–30). Rodziny: adapter 1945, driver_rod 1337, blade_jigsaw 715, extension 292, grease 200, chisel_bush 166, other 123, chisel_flat 99, driver_pile 72, auger 72, set_adapter 70, set_chisel 62.
* Rodziny występujące **tylko w paczkach**: adapter, drill_bit, blade_jigsaw, grease, chisel_bush, set_chisel, set_adapter, handle, pin, chisel_point.

---

## 6. Wolumen miesięczny i sezonowość

### 6.1 Sztuki i wysyłki wg roku i miesiąca

Sztuki:

| m-c | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| 01 | – | 3751 | 2477 | 2148 | 1767 | 1962 | 1223 |
| 02 | – | 3209 | 3667 | 1840 | 3106 | 4349 | 2158 |
| 03 | – | 5128 | 3442 | 3579 | 2813 | 4192 | **7138** |
| 04 | – | 4458 | 2630 | 3627 | 4202 | 3594 | 6807 |
| 05 | – | 1144 | 3383 | 3673 | 3063 | 3356 | 4319 |
| 06 | – | brak pliku | 2494 | 5621 | 3423 | 3508 | 5078 |
| 07 | – | brak pliku | 2048 | 2099 | 2393 | 4626 | 5087 |
| 08 | – | 1587 | 3667 | 1717 | 2490 | 2207 | 5056 |
| 09 | 3044 | 2975 | 2632 | 3107 | 2809 | 3297 | – |
| 10 | 2160 | 1296 | 2247 | 3509 | 2272 | 3427 | – |
| 11 | 2844 | 726 | 1696 | 2149 | 1756 | 2435 | – |
| 12 | 1796 | 1813 | 984 | 2359 | 2067 | 935 | – |
| **rok** | 9844 (4 m.) | 26087 (10 m.) | 31367 | 35428 | 32161 | 37888 | 36866 (8 m.) |

Wysyłki:

| m-c | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| 01 | – | 56 | 58 | 39 | 50 | 34 | 32 |
| 02 | – | 54 | 61 | 33 | 53 | 82 | 53 |
| 03 | – | 54 | 63 | 67 | 50 | 63 | **135** |
| 04 | – | 45 | 48 | 65 | 90 | 73 | 120 |
| 05 | – | 13 | 60 | 56 | 56 | 79 | 90 |
| 06 | – | – | 56 | 112 | 57 | 57 | 116 |
| 07 | – | – | 52 | 52 | 36 | 93 | 116 |
| 08 | – | 38 | 68 | 53 | 54 | 38 | 108 |
| 09 | 95 | 57 | 59 | 65 | 51 | 76 | – |
| 10 | 55 | 30 | 51 | 83 | 48 | 71 | – |
| 11 | 50 | 28 | 33 | 43 | 35 | 63 | – |
| 12 | 55 | 60 | 25 | 37 | 47 | 37 | – |
| **rok** | 255 | 435 | 634 | 705 | 627 | 766 | 770 |

Kwartalnie (szt.): 2022: 9586 / 8507 / 8347 / 4927; 2023: 7567 / 12921 / 6923 / 8017; 2024: 7686 / 10688 / 7692 / 6095; 2025: 10503 / 10458 / 10130 / 6797; 2026: 10519 / **16204** / 10143 (VII–VIII). Ostatnie 12 miesięcy (2025-09 … 2026-08): **46 960 szt. w 1017 wysyłkach** vs poprzednie 12 m.: 36 698 szt. / 700 wysyłek (**+28 % szt., +45 % wysyłek**; średnia wielkość wysyłki spadła z 52,4 do 46,2 szt.). Reżim polski, udział WRO5 w sztukach: 2024 II poł. 0,49–0,75; 2025: 0,44–0,75 (najniżej III 0,44, najwyżej XI 0,75); 2026: I 0,70, II 0,78, III 0,46, IV 0,52, V 0,54, VI 0,60, VII 0,56, VIII 0,59 – w szczycie sezonu (III–IV) XPO1 (świdry, palety) dorównuje WRO5.

### 6.2 Indeks sezonowości (średnia z lat 2022–2025; 1,00 = przeciętny miesiąc)

| m-c | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sztuki | 0,74 | 1,14 | 1,23 | 1,24 | 1,19 | **1,31** | 0,96 | 0,90 | 1,04 | 1,00 | 0,70 | **0,56** |
| wysyłki | 0,81 | 1,00 | 1,07 | 1,22 | 1,10 | 1,24 | 1,00 | 0,95 | 1,10 | 1,10 | 0,75 | 0,65 |

Szczyt luty–czerwiec (ok. 60 % rocznych sztuk w I–II kwartale: 2022: 57,7 %, 2023: 57,8 %, 2024: 57,1 %, 2025: 55,3 %), dołek listopad–styczeń.

### 6.3 Sezonowość i trend wg rodzin

Sztuki rocznie (udział w roku):

| Rodzina | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 (8 m.) | udział 2025 → 2026 |
|---|---|---|---|---|---|---|---|
| auger | 3756 | 6272 | 7053 | 6018 | 9174 | **11968** | 24,2 % → **32,5 %** |
| adapter | 4484 | 5852 | 6474 | 8575 | 9235 | 7808 | 24,4 % → 21,2 % |
| driver_rod | 22 | 1160 | 5954 | 4503 | 4337 | 4244 | 11,4 % → 11,5 % |
| drill_bit | 7327 | 7859 | 6434 | 3541 | 1680 | 744 | 4,4 % → 2,0 % (z 34,9 % w 2020) |
| other | 876 | 1367 | 123 | 2721 | 4266 | 1811 | 11,3 % → 4,9 % |
| extension | 1117 | 2029 | 2522 | 1859 | 1270 | 2306 | 3,4 % → 6,3 % |
| chisel_flat | 339 | 385 | 139 | 607 | 1451 | 2161 | 3,8 % → 5,9 % |
| blade_jigsaw | 3607 | 2117 | 3361 | 1463 | 2256 | 1490 | 6,0 % → 4,0 % |
| driver_pile | 139 | 623 | 861 | 1316 | 1433 | 1096 | 3,8 % → 3,0 % |
| grease | 0 | 0 | 0 | 0 | 267 | 1195 | 0,7 % → 3,2 % (nowość od IV 2025) |
| chisel_bush | 0 | 0 | 0 | 0 | 399 | 495 | nowość od II 2025 |
| chisel_spade | 1416 | 1895 | 1226 | 789 | 724 | 30 | wygaszany |
| set_chisel | 290 | 306 | 124 | 166 | 489 | 471 | 1,3 % |
| blade_recip / chisel_point / saw_disc | 1626 / 415 / 347 | 275 / 863 / 132 | 201 / 688 / 0 | 114 / 277 / 0 | 152 / 102 / 0 | 93 / 141 / 8 | marginalne |

Indeks sezonowy sztuk wg rodzin (2022–2025; udział kwartałów Q1/Q2/Q3/Q4 w %):

| Rodzina | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | Q1/Q2/Q3/Q4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| auger | 0,87 | **1,60** | 1,30 | 1,28 | 1,36 | 1,21 | 1,05 | 0,78 | 0,86 | 0,71 | **0,45** | 0,53 | 31 / 32 / 23 / 14 |
| adapter | 0,47 | 0,94 | 1,34 | **1,63** | 1,37 | 1,44 | 0,82 | 1,09 | 1,01 | 0,85 | 0,63 | **0,40** | 23 / 37 / 24 / 16 |
| drill_bit | 1,10 | 1,48 | 1,13 | 0,87 | 0,91 | 1,19 | 0,72 | 0,80 | 1,01 | 1,31 | 0,72 | 0,76 | 30 / 25 / 23 / 22 |
| driver_rod | 0,36 | 0,89 | 0,91 | 0,84 | 1,09 | 1,04 | **1,52** | 0,72 | 1,26 | **1,35** | 1,21 | 0,82 | 21 / 28 / 27 / 24 |
| blade_jigsaw | 0,51 | 1,09 | 1,42 | 1,54 | 0,88 | 1,03 | 0,58 | 0,93 | 1,18 | 1,35 | 1,00 | 0,49 | 23 / 28 / 24 / 26 |
| extension | 1,06 | 1,37 | 1,15 | 1,36 | **1,54** | 1,29 | 0,87 | 0,86 | 0,91 | 1,02 | 0,31 | 0,26 | 30 / 36 / 20 / 13 |
| driver_pile | 0,24 | 0,52 | 0,60 | 1,55 | 0,57 | **2,47** | 1,67 | 0,54 | 1,46 | 0,84 | 0,84 | 0,70 | 13 / 36 / 32 / 20 |
| chisel_flat | 1,09 | 1,16 | 1,06 | 0,51 | 0,60 | 1,00 | 0,69 | 1,21 | 1,35 | 1,29 | 1,34 | 0,71 | 23 / 23 / 29 / 25 |
| chisel_spade | 0,96 | 1,30 | 1,21 | 1,33 | 1,25 | 0,64 | 0,78 | 0,74 | 1,34 | 1,36 | 0,43 | 0,67 | 29 / 26 / 23 / 22 |
| set_chisel | 1,17 | 0,87 | 0,96 | 1,03 | 0,88 | 1,21 | 0,94 | 0,59 | 1,28 | 1,34 | 0,69 | 1,04 | 22 / 25 / 26 / 27 |
| other | 1,28 | 0,61 | 1,02 | 0,91 | 0,99 | 0,85 | 0,85 | 1,10 | 0,64 | 2,71 | 0,60 | 0,45 | 25 / 28 / 28 / 19 |

Wnioski: **świdry, przedłużki i adaptery są silnie wiosenne** (luty–czerwiec; listopad–styczeń 0,3–0,5), **pobijaki i dłuta płaskie mają drugi szczyt jesienią** (wrzesień–listopad ≈ 1,2–1,35), **wbijaki do pali – lato** (czerwiec 2,47, lipiec 1,67). Wiertła i zestawy dłut są prawie płaskie. Dla planera dopełnień: zimą (XI–I) trudno dopełnić paletę XPO1 świdrami, ale popyt na pobijaki/dłuta (WRO5) trzyma się; wiosną obie klasy rosną, a udział XPO1 w sztukach rośnie do ~50 %.

Rok 2026 w rodzinach (szt. I–VIII): auger 192 / 202 / **2988** / **3029** / 988 / 1532 / 1699 / 1338; adapter 351 / 570 / 1565 / 946 / 1507 / 854 / 1068 / 947; driver_rod 119 / 247 / 682 / 906 / 279 / 634 / 551 / 826; extension 44 / 206 / 387 / 198 / 231 / 325 / 452 / 463; chisel_flat 30 / 371 / 355 / 290 / 255 / 472 / 146 / 242; blade_jigsaw 20 / 60 / 30 / 115 / 40 / 510 / 450 / 265; grease 125 / 100 / 170 / 300 / 200 / 100 / 0 / 200.

---

## 7. Parametry do narzędzia (podsumowanie)

| Parametr | Wartość | Źródło |
|---|---|---|
| Paczka FBA – sztuki (2026-07/08) | mediana 20; p25 10; p75 45; p90 89; max 200; 1 produkt w 68 % | §1.3 |
| Paczka → **WRO5** | mediana 40 (p25 15, p75 69, p90 112, max 200); 1–5 produktów | §1.3 |
| Paczka → **XPO1** | mediana 14 (p25 7, p75 20, p90 26, max 50); 1 produkt w 84 % | §1.3 |
| Paleta – sztuki | mediana 148,5; p25 126; p75 173,5; min 80; max 210; średnio 150 | §1.3 |
| Paleta – linie / produkty | 6 linii (3–7); 4 produkty (2–5); ~25 szt./linię | §1.3, §5 |
| Paleta – FC | 19/22 XPO1 (świdry + przedłużka 1000/5000 mm), 3/22 WRO5 (wbijaki, dłuta HEX30, pobijaki) | §5 |
| Palet miesięcznie | 11 (VII 2026) i 11 (VIII 2026); proxy xlsx: 1–14/mies. | §5 |
| Wysyłka reżimu polskiego – WRO5 | mediana 45,5 szt. (p25 25, p75 85, p90 133, max 250); 2 linie | §1.2 |
| Wysyłka reżimu polskiego – XPO1 | mediana 16 szt. (p25 10, p75 30, p90 138, max 247); 1 linia; ≥ 100 szt. w 14,5 % | §1.2 |
| Próg „paleta” na XPO1 | ≥ 100 szt. lub ≥ 5 linii (mediana sztuk skacze 37,5 → 108) | §1.2 |
| Plany (10 min) | 9,6 % planów wieloprzesyłkowych; 28 % z nich (2,7 % wszystkich) rozdzielone WRO5+XPO1 | §2.2 |
| Podział sztuk w planie rozdzielonym | WRO5 mediana 74 % (IQR 51–85 %); XPO1 dostaje 21 szt. (mediana), WRO5 55 | §2.2 |
| Dzielenie jednego SKU między FC | 1 przypadek na 165 (praktycznie nie) | §2.2 |
| Rodziny → FC | 100 % WRO5: driver_rod, driver_pile, blade_jigsaw, chisel_bush, grease, tamper, spring, pin, string, set_adapter; ≥ 89 %: adapter (0,89); XPO1: auger 0,93, drill_bit 0,89, set_chisel 0,93, chisel_point 0,85, handle 1,00; mieszane: chisel_flat 0,38 WRO5, extension 0,69 WRO5, other 0,54 | §2.3 |
| Ilość na linii | mediana 12 (p25 7, p75 24, p90 40); WRO5 podz. przez 10: 51 %, XPO1: 24 % | §3.1 |
| Karton świdrów wg Ø | 40: 15 (lub 13); 50: 14; 60: 13 (SDS Max 12); 80: 11; 100: 10; 120: 9; 150: 7; 200: 6 | §3.3 |
| Kartony innych | przedłużka 400: 34; 750 SDS Max: 14; 1180 SDS Max: 9; 1000 SDS Max: 10; 1000 (świder): 30; 600: 24; 800: 20; 5000: 4; dłuto 75×600 SDS Max: 14; 110×410 SDS Max: 7; szypa 135×410: 29; wiertło 40×600: 7; smar: 100; brzeszczoty T744D 5 szt.: 50; adaptery: 10 (partie 20–50); pobijak 20,2×165 SDS Max: 56–60; pobijaki 13,5 SDS Plus: 100 | §3.2–3.3 |
| Produkty „solo” (główne) | extension|l400 (34), chisel_flat|d75|l600|sds_max (14), auger|d100|l600 (20), auger|d60|l600 (26), driver_rod|d20.2|l165|sds_max (56), set_chisel|sds_plus|n3 (10), extension|l750|sds_max (14) | §4.3 |
| Produkty „dopełniacze” (nigdy solo) | świdry SDS Ø 100–150 (moduł 7–10), adapter|m14|unf_1_2, extension|l120|m14, driver_rod 16,5/32,5 SDS Plus, chisel_bush, pin, blade_jigsaw|T744D|l180 | §4.4 |
| Sezonowość | szczyt II–VI (indeks 1,14–1,31), dołek XI–I (0,56–0,74); świdry II–VI, pobijaki/dłuta VII i IX–XI, wbijaki VI–VII | §6 |
| Trend | ostatnie 12 m.: 46 960 szt./1017 wysyłek (+28 % / +45 % r/r); auger 32,5 % sztuk 2026 (24 % w 2025), drill_bit spadł do 2 % | §6 |
