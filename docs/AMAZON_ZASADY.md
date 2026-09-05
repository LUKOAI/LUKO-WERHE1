# Zasady Amazon FBA (EU / Polska) istotne dla planowania wysyłek

Stan: wrzesień 2026. Zebrane z oficjalnych stron Seller Central (przez indeks wyszukiwarki — bezpośredni dostęp był zablokowany), kart opłat EU 2025–2026, Carrier SOP Pan-EU (12.2025), oficjalnego modelu SP-API (GitHub `amzn/selling-partner-api-models`) i z danych własnych klienta. Poziom pewności: **[W]** wysoki (kilka zgodnych źródeł oficjalnych), **[Ś]** średni (jedno źródło lub źródło pośrednie), **[N]** niski (źródła nieoficjalne / niezweryfikowane). Pozycje **do potwierdzenia na koncie klienta** oznaczono ⚠.

## 1. Karton (SPD, także kartony na palecie)

| Zasada | Wartość | Pewność |
|---|---|---|
| Maks. bok kartonu z wieloma sztukami | 63,5 cm (każdy bok). W 06.2025 podniesiono do 91,4 cm dla UK/FR/DE/IT/ES, w 10.2025 cofnięto do 63,5 cm | [W] |
| Wyjątek | karton może być dłuższy, jeśli zawiera **jedną** sztukę oversize dłuższą niż 63,5 cm | [W] |
| Maks. masa | 23 kg (dawniej 30 kg); wyjątek: pojedyncza sztuka oversize cięższa niż 23 kg | [W] |
| Etykieta „ciężka paczka / Team Lift” | > 15 kg, 5 etykiet (góra + 4 boki) | [W] |
| Minimum | 15,2 × 10 × 2,5 cm, 0,15 kg | [Ś] |
| Mieszanie klas | karton ze sztukami standard-size nie może zawierać sztuk oversize (pakowane i kierowane osobno) | [N] (US) — potwierdzone empirycznie: 0 wysyłek mieszanych w 1 848 |
| Limit kartonów w wysyłce SPD | 200 (przewoźnik partnerski) / 500 (własny) | [Ś] |
| Brak informacji o zawartości kartonu | opłata manualnego przetwarzania ok. 0,18 €/szt. | [Ś] |

## 2. Paleta

| Zasada | Wartość | Pewność |
|---|---|---|
| Typ | tylko EUR/CHEP 80 × 120 cm (EPAL / EN 13698-1), nieuszkodzona, niemalowana; ISPM-15 przy transporcie międzynarodowym | [W] |
| Wysokość | maks. **180 cm** z paletą (help G200141510; Carrier SOP 12.2025). Starsze polskie poradniki podają 170 cm — nieaktualne | [W] |
| Masa | **500 kg** brutto z paletą (reguła FBA); Carrier SOP dopuszcza do 1 350 kg dla dostaw przewoźników z etykietą „heavy pallet” — do planowania używać 500 kg | [W] |
| Piętrowanie | tylko w FC z tabeli „FC Specifics”, do 3,0 m łącznie, palety spięte; XPO1 wg strony przewoźnika „do 3,0 m, jeśli bezpieczny rozładunek” ⚠ | [Ś] |
| Folia | przezroczysta stretch (czarna może być odrzucona), min. 3 owinięcia, ładunek stabilny bez folii; dopuszczalne taśmy na palecie, nie na kartonach | [W] |
| Etykiety | 4 etykiety palety (każdy bok) na folii; każdy karton z własną etykietą FBA | [W] |
| Jedna wysyłka na paletę | wszystkie sztuki na palecie muszą należeć do jednego shipment ID | [W] |
| Nawis | brak nawisu poza 80 × 120; najcięższe kartony na dole, układ „w cegiełkę” | [Ś] |
| Dostawa LTL/FTL do PL | awizacja przez Carrier Central z 24-godzinnym wyprzedzeniem (WRO1, WRO2, POZ1, SZZ1, WRO5, XPO1), list przewozowy (BOL) | [Ś] |

## 3. Klasy rozmiaru (karta opłat EU 2026)

Waga objętościowa = L × W × H [cm] / 5000. Dla paczek i oversize liczy się większa z wag (rzeczywista / objętościowa); koperty i special oversize — tylko rzeczywista.

| Klasa | Maks. wymiary | Maks. masa | Sieć |
|---|---|---|---|
| Lekka / standardowa / duża / XL koperta | 33 × 23 × 2,5 / 2,5 / 4 / 6 cm | 0,1 / 0,46 / 0,96 / 0,96 kg | standard (sortable) |
| Mała paczka | 35 × 25 × 12 cm | 3,9 kg (obj. 2,1) | standard |
| **Paczka standardowa** | **45 × 34 × 26 cm** | **11,9 kg** (obj. 7,96) | standard |
| Mała ponadwymiarowa | 61 × 46 × 46 cm | 1,76 kg (obj. 25,82) | oversize (non-sortable) |
| Standardowa ponadwymiarowa | 120 × 60 × 60 cm | 29,76 kg (obj. 86,4) | oversize |
| Duża ponadwymiarowa | 150 × 60 × 60 cm | 31,5 kg (obj. 108) | oversize |
| Specjalna ponadwymiarowa | > 175 cm lub > 31,5 kg lub obwód > 360 cm | — | oversize / H&B |

Pewność [W] dla progów paczek i oversize (kilka wydań karty), [Ś] dla dużej ponadwymiarowej (dwa sformułowania w kartach DE/EN). Uwaga: popularne blogi z 2026 podają błędne tabele („small standard ≤ 1 kg, medium oversize ≤ 30 kg”) — nie używać.

**Wniosek dla planera:** granica 45 cm najdłuższego boku paczki standardowej pokrywa się dokładnie z podziałem w danych klienta: produkty ≥ 46 cm → XPO1 (non-sortable), < 40 cm → WRO5 (sortable), 40–46 cm zależy od wymiarów opakowania zarejestrowanych dla ASIN-u. Szczegóły: `docs/analiza/fc_rules.md`.

## 4. Podział planu na magazyny (Send to Amazon)

* Amazon **dzieli plan wg produktów** („fulfillment centers are selected based on the products you're shipping and where you're shipping them from”); podział widać w kroku 2 „Potwierdź wysyłkę”, po zatwierdzeniu informacji o pakowaniu; po akceptacji nie da się cofnąć — trzeba anulować i utworzyć plan od nowa. [W]
* W USA istnieją płatne opcje „minimal / partial / Amazon-optimized splits” (opłata placement od 03.2024). **W EU (DE/PL/FR/IT/ES/UK) tej opłaty i wyboru nie ma** — odpowiedź pracownika Amazon na forum EU (01.2025), brak pozycji w kartach opłat 2026. ⚠ Warto potwierdzić zrzutem ekranu kroku 2 z konta klienta. [Ś]
* Reguła „5 identycznych kartonów na SKU” dla podziału bez opłaty dotyczy USA; analog EU nieznany. [N]
* Sprzedawca **nie może wskazać magazynu** (`customPlacement` w API tylko dla Indii). Dźwignie: skład planu (SKU i ilości), pakowanie (karton vs paleta), adres nadania, wybór spośród zwróconych opcji. [W]
* Empirycznie (dane klienta 2024–2026): Amazon nigdy nie miesza klas w jednej wysyłce, nie dzieli ilości jednego SKU między FC (1 przypadek na 165), plan dwóch klas → dwie wysyłki (WRO5 + XPO1). Palety jadą prawie wyłącznie do XPO1 (19/22). [W — dane własne]
* Nowy długi ASIN bez zweryfikowanych wymiarów bywa przy pierwszej wysyłce kierowany jak „sortable” (WRO5); po pomiarze w FC klasa się zmienia. [Ś — 3 przypadki w danych]

## 5. Limity pojemności (Capacity limits)

* Od 03.2023 jeden miesięczny limit pojemności per typ magazynowania (standard, oversize, odzież, obuwie), w **m³** w EU (ft³ w UK/US). [W]
* Zużycie = zapas w FC **+ otwarte (utworzone, niedostarczone) wysyłki** — pojemność jest zużywana w momencie **utworzenia** wysyłki. Niepotrzebne plany anulować; Amazon może sam anulować wysyłki ponad limit. [W]
* Limit na kolejny miesiąc ogłaszany w trzecim pełnym tygodniu miesiąca (+ szacunki na 2 kolejne); widoczny w Capacity Monitor (dół pulpitu FBA, także w Send to Amazon). Konta Professional < 39 tygodni FBA — bez limitu. [W]
* Capacity Manager: dodatkowa pojemność w aukcji za opłatę rezerwacyjną per m³ (przyznawana ~2×/tydz.). [W]
* Kwota opłaty za przekroczenie (EUR/m³) w EU — nieustalona ⚠.

## 6. SP-API Fulfillment Inbound v2024-03-20 (symulacja podziału bez tworzenia wysyłki)

* Stare v0 `createInboundShipmentPlan` usunięte 21.01.2025; pozostały odczyty v0 (`getShipments` zwraca `DestinationFulfillmentCenterId`, np. WRO5/XPO1). [W]
* Przepływ „paleta / karton nieznany” (Pack Later): `createInboundPlan` → `generatePlacementOptions` → `listPlacementOptions` → (`confirmPlacementOption`) → `setPackingInformation` → `generateTransportationOptions` → … Wszystkie POST są asynchroniczne (`operationId`, `getInboundOperationStatus`). [W]
* `PlacementOption` = „shipment splits and destinations of SKUs”: `shipmentIds[]`, `fees[]`/`discounts[]` (target „Placement Services”), `status OFFERED/ACCEPTED/EXPIRED`, `expiration` (praktycznie ~72 h). Kod magazynu: `getShipment(...).destination.warehouseId` (może być pusty dla `AMAZON_OPTIMIZED`); pozycje: `listShipmentItems`. **Opcje można wygenerować i odczytać bez potwierdzania**, plan roboczy anulować `cancelInboundPlan` (opłaty dotyczą tylko potwierdzonego transportu partnerskiego). [W]
* Zgłoszenia sprzedawców: API często zwraca tylko jedną opcję (lub dwie identyczne) tam, gdzie Seller Central pokazuje kilka; `generatePlacementOptions` trwa 10–20 min i bywa niestabilne; niepublikowany limit 10 000 szt. na plan; jeden przewoźnik dla wszystkich wysyłek planu (FBA_INB_0354). [Ś]
* Limity: `createInboundPlan` 2 rps (burst 2), `items` ≤ 2000, `quantity` 1–500 000, `destinationMarketplaces` dokładnie 1 (DE `A1PA6795UKMFR9`, PL `A1C3SOZRARQ6R3`). Rola „Amazon Fulfillment” w aplikacji deweloperskiej, token LWA sprzedawcy. [W]
* Adapter w `fbaplan/spapi/inbound.py` implementuje ten przepływ (nietestowany bez kluczy) ⚠.

## 7. Sieć magazynów w Polsce (kontekst)

* **WRO5** — Okmiany 3C, 59-225 (gm. Chojnów, przy A4); Amazon Fulfillment Poland sp. z o.o.; otwarty 11.2019 jako centrum „flow-through”. W danych klienta: wyłącznie produkty krótkie (sortable). [W — adres z dokumentów klienta]
* **XPO1** — Nowa Niedrzwica 58, 66-340 Przytoczna (lubuskie), operator ID Logistics Poland (3PL, prefiks „X”); tylko palety EUR, Carrier Central 24 h. W danych klienta: wyłącznie produkty długie (non-sortable) i prawie wszystkie palety. Alias „XPLD” niepotwierdzony. [W — adres z dokumentów klienta]
* Inne PL: WRO1/2/3/4 Bielany Wrocławskie, POZ1 Sady, POZ2 Świebodzin, SZZ1 Kołbaskowo, KTW1 Sosnowiec, KTW3 Gliwice, LCJ2–4 Łódź/Pawlikowice, XWR3 Krzyżowice. W reżimie polskim (od 06.2024) 99,1 % wysyłek klienta poszło do WRO5/XPO1; WRO2/POZ1 pojawiły się raz (10.2024, przelew WRO5). [Ś]
* Reżim niemiecki (06.2022–05.2024): sortable = HAJ1, DTM2; non-sortable = DTM1, LEJ3, STR1, DUS2, LEJ1, XSC1, XFR2, XDU2. Podział identyczny jak w PL. [W — dane własne]
* Program Europa Środkowa (CEP): bez udziału +1,15 zł / 0,26 € za sztukę wysyłaną z niemieckich FC; udział bezpłatny (magazynowanie w PL/CZ). [Ś]

## 8. Opłaty istotne dla decyzji paleta vs paczki

* W EU brak opłaty placement; koszt to fracht (paleta LTL vs paczki SPD), ewentualnie dopłata paliwowa 1,5 % do opłat realizacji (od 04.2026), opłata za niski stan zapasów (Pan-EU, tylko standard-size, < 28 dni pokrycia). [Ś]
* Amazon-partnered carrier zwykle tańszy niż własny; anulowanie transportu partnerskiego bez kosztów w ciągu 24 h (SPD) / 1 h (LTL). [Ś]
* Stawki frachtu klienta (paleta / paczka) wpisać w **Ustawieniach** narzędzia — wtedy plan pokazuje koszt/szt.

## 9. Otwarte pytania (do potwierdzenia z klientem / na koncie)

1. Czy krok 2 Send to Amazon na amazon.de/pl pokazuje jakiekolwiek opcje podziału, czy tylko jeden podział Amazona? (zrzut ekranu)
2. Wymiary opakowań i klasa rozmiaru per SKU (eksport „Podgląd opłat”) — do wpisania w `data/products.csv`; rozstrzyga szarą strefę 40–46 cm.
3. Czy klient ma zgodę na magazynowanie w PL/CZ (CEP) i jaki jest bieżący limit pojemności (m³) standard / oversize.
4. Czy zestaw „35/50 × 410 Hex30” ma dwa ASIN-y (raz WRO5, raz XPO1)?
5. Dostęp SP-API (aplikacja deweloperska + refresh token) — czy klient chce symulacji podziału przez API.
