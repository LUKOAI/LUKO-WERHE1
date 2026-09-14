from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from app.apilo_client import ApiloClient
from app.apilo_auth import ensure_valid_token
from app.config import AppConfig
from app.filtering import prefilter_non_eu, qualifies_for_tax_bundle, is_non_eu, is_pl_invoice_number, has_pl_invoice
from app.models import OrderRecord, ProcessingResult
from app.pdf_generator import generate_order_pdf, generate_summary_pdf, merge_pdfs
from app.summary_export import export_summary_xlsx
from app.tracking_capture import capture_tracking_screenshot
from app.browser_session import CaptureSession, has_session
from app.amazon_capture import (
    build_amazon_order_url, download_amazon_pl_invoices, NA_COUNTRIES,
    is_amazon_order_number,
)
from app.apilo_panel_capture import build_apilo_order_url


ProgressCallback = Callable[[int, int], None]
LogCallback = Callable[[str], None]


@dataclass
class PipelineOutput:
    output_dir: Path
    processed: list[ProcessingResult]
    summary_pdf: Path
    summary_xlsx: Path


TRACKING_URLS = {
    "UPS": "https://www.ups.com/track?tracknum={tn}",
    "DPD": "https://tracktrace.dpd.com.pl/parcelDetails?typ=1&p1={tn}",
    "DHL": "https://www.dhl.com/pl-en/home/tracking.html?tracking-id={tn}",
    "FEDEX": "https://www.fedex.com/fedextrack/?trknbr={tn}",
    "GLS": "https://gls-group.com/PL/pl/sledzenie-paczek?match={tn}",
    "INPOST": "https://inpost.pl/sledzenie-przesylek?number={tn}",
    "POCZT": "https://emonitoring.poczta-polska.pl/?numer={tn}",
}


class DocumentPipeline:
    def __init__(self, config: AppConfig, logger) -> None:
        self.config = ensure_valid_token(config)
        self.logger = logger
        self.client = ApiloClient(self.config)

    @staticmethod
    def _guess_courier_from_tracking(tracking_number: str) -> str:
        """Rozpoznaje kuriera po formacie numeru przesylki.

        1Z...            -> UPS
        XX#########PL    -> Poczta Polska (np. CP919979907PL)
        14 cyfr          -> DPD (np. 13349351985767)
        """
        import re
        tn = (tracking_number or "").strip().upper()
        if not tn:
            return ""
        if tn.startswith("1Z"):
            return "UPS"
        if re.fullmatch(r"[A-Z]{2}\d{9}PL", tn):
            return "POCZTA POLSKA"
        if re.fullmatch(r"\d{14}", tn):
            return "DPD"
        return ""

    @staticmethod
    def _build_tracking_url(courier: str, tracking_number: str) -> str:
        courier_upper = courier.upper().split()[0]
        for key, tmpl in TRACKING_URLS.items():
            if key in courier_upper:
                return tmpl.format(tn=tracking_number)
        return ""

    @staticmethod
    def _safe_filename(name: str) -> str:
        for ch in '/\\:*?"<>|':
            name = name.replace(ch, "_")
        return name.strip() or "faktura"

    @staticmethod
    def _browser_dead(exc: Exception) -> bool:
        """Czy wyjatek oznacza, ze przegladarka padla / zostala zamknieta."""
        msg = str(exc).lower()
        return any(k in msg for k in (
            "has been closed", "browser has been closed", "target closed",
            "connection closed", "disconnected", "not open", "closed",
        ))

    def _restart_session(self, old, site: str, log):
        """Zamyka padnieta sesje i otwiera nowa. Zwraca nowa sesje lub None."""
        try:
            old.__exit__(None, None, None)
        except Exception:
            pass
        try:
            new = CaptureSession(site, self.config, headless=False)
            new.__enter__()
            log(f"  Przegladarka ({site}) otwarta ponownie — kontynuuje.")
            return new
        except Exception as exc:
            log(f"  Nie udalo sie ponownie otworzyc przegladarki ({site}): {str(exc)[:120]}")
            return None

    def _download_pl_invoice(self, order: OrderRecord, folder: Path,
                             idx: int, total: int, log) -> Path | None:
        """Pobiera fakture(y) z prefiksem PL. Zwraca sciezke do (polaczonego) PDF faktur."""
        try:
            docs = self.client.fetch_order_documents(order.order_id)
        except Exception as exc:
            log(f"[D {idx}/{total}] Nie pobrano listy faktur: {exc}")
            return None
        downloaded: list[Path] = []
        for doc in docs:
            number = str(doc.get("number") or "")
            # Faktura PL z Apilo = dokument typu 2 (faktura VAT, numer typu "7/04/2026/0")
            if doc.get("type") != 2 and not is_pl_invoice_number(number):
                continue
            fname = f"faktura_{self._safe_filename(number)}.pdf"
            out = self.client.download_document_file(doc, folder / fname, order_id=order.order_id)
            if out:
                log(f"[D {idx}/{total}] Pobrano fakture PL: {number}")
                downloaded.append(out)
            else:
                log(f"[D {idx}/{total}] Faktura PL {number} — brak pliku/media")
        if not downloaded:
            return None
        if len(downloaded) == 1:
            return downloaded[0]
        # kilka faktur — polacz w jedna
        try:
            from pypdf import PdfReader, PdfWriter
            writer = PdfWriter()
            for f in downloaded:
                for page in PdfReader(str(f)).pages:
                    writer.add_page(page)
            combined = folder / "faktury_PL.pdf"
            with open(combined, "wb") as fh:
                writer.write(fh)
            return combined
        except Exception:
            return downloaded[0]

    def run(
        self,
        date_from: date,
        date_to: date,
        test_mode: bool = False,
        selected_apilo_numbers: set[str] | None = None,
        selected_amazon_numbers: set[str] | None = None,
        progress_cb: ProgressCallback | None = None,
        log_cb: LogCallback | None = None,
    ) -> PipelineOutput:
        month_label = f"{date_from.strftime('%Y_%m')}"
        output_dir = Path(self.config.output_root) / f"PDFy_{month_label}"
        # DO_WYDRUKU: tylko gotowe PDF-y zamowien spelniajacych kryteria + podsumowania
        # DO_KONTROLI: wszystkie zebrane materialy robocze (screenshoty, pojedyncze
        #              faktury, pliki DEBUG/INVALID, materialy zamowien pominietych)
        print_dir = output_dir / "DO_WYDRUKU"
        kontrola_dir = output_dir / "DO_KONTROLI"
        output_dir.mkdir(parents=True, exist_ok=True)
        print_dir.mkdir(parents=True, exist_ok=True)
        kontrola_dir.mkdir(parents=True, exist_ok=True)

        def log(msg: str) -> None:
            self.logger.info(msg)
            if log_cb:
                log_cb(msg)

        log(f"Pobieranie zamówień z zakresu {date_from} - {date_to}...")
        raw_orders = self.client.fetch_orders(date_from.isoformat(), date_to.isoformat())
        log(f"Pobrano rekordów: {len(raw_orders)}")

        # Krok 1: Wstępne filtrowanie po kraju (poza UE)
        log("Wstepne filtrowanie po kraju (poza UE)...")
        preliminary: list[tuple[dict, OrderRecord]] = []
        for i, raw in enumerate(raw_orders, 1):
            record = self.client.to_order_record(raw)
            if prefilter_non_eu(record):
                preliminary.append((raw, record))
            if i % 200 == 0:
                log(f"  Przeanalizowano {i}/{len(raw_orders)}...")

        log(f"Po wstepnym filtrze: {len(preliminary)} z {len(raw_orders)}")

        # Krok 1b: Reczny wybor numerow PRZED pobieraniem szczegolow
        # (numery Apilo = id, numery Amazon = idExternal — oba sa juz w danych listy;
        # bez tego pobieralibysmy szczegoly tysiecy zamowien niepotrzebnie)
        apilo_query = {v.strip().lower() for v in (selected_apilo_numbers or set()) if v.strip()}
        amazon_query = {v.strip().lower() for v in (selected_amazon_numbers or set()) if v.strip()}
        if apilo_query or amazon_query:
            def matches_prelim(rec: OrderRecord) -> bool:
                if apilo_query and (rec.order_number.strip().lower() in apilo_query
                                    or rec.order_id.strip().lower() in apilo_query):
                    return True
                if amazon_query and rec.amazon_order_number.strip().lower() in amazon_query:
                    return True
                return False
            preliminary = [(raw, rec) for raw, rec in preliminary if matches_prelim(rec)]
            log(f"Po wstepnej selekcji numerow: {len(preliminary)}")

        # Krok 2: Pobieranie szczegółów TYLKO dla kwalifikujących się zamówień
        records: list[OrderRecord] = []
        for i, (raw, _) in enumerate(preliminary, 1):
            oid = str(raw.get("id") or raw.get("order_id") or raw.get("orderId") or "")
            if oid:
                log(f"  Pobieranie szczegółów {i}/{len(preliminary)}: {oid}")
                try:
                    details = self.client.fetch_order_details(oid)
                    record = self.client.to_order_record(raw, details)
                except Exception:
                    record = self.client.to_order_record(raw)
            else:
                record = self.client.to_order_record(raw)
            records.append(record)

        # Krok 3: Ponowne filtrowanie po wzbogaceniu danymi
        filtered = [r for r in records if qualifies_for_tax_bundle(r)]
        log(f"Po filtrach (poza UE + faktura .pl + tracking): {len(filtered)}")

        # Krok 3b: Reczny wybor numerow — powtorka po wzbogaceniu danymi
        # (wstepna selekcja byla w Kroku 1b; ta laczy dane ze szczegolow)
        if apilo_query or amazon_query:
            preselected_count = len(filtered)

            def matches_selection(order: OrderRecord) -> bool:
                apilo_match = bool(
                    apilo_query
                    and (
                        order.order_number.strip().lower() in apilo_query
                        or order.order_id.strip().lower() in apilo_query
                    )
                )
                amazon_match = bool(
                    amazon_query and order.amazon_order_number.strip().lower() in amazon_query
                )
                return apilo_match or amazon_match

            filtered = [r for r in filtered if matches_selection(r)]
            log(
                "Po ręcznym wyborze numerów "
                f"(Apilo: {len(apilo_query)}, Amazon: {len(amazon_query)}): "
                f"{len(filtered)} z {preselected_count}"
            )

        if test_mode:
            filtered = filtered[:5]
            log("Tryb testowy aktywny: przetwarzam tylko 5 pierwszych zamówień.")

        # Krok 4: Wyszukanie numerow tracking + daty dostawy (tylko dla wybranych OWN)
        own_orders_ids = {r.order_id for r in filtered if r.warehouse_type != "fba"}
        if own_orders_ids:
            log(f"Szukanie trackingu dla {len(own_orders_ids)} zamowien (magazyn wlasny)...")
            tracking_map = self.client.fetch_tracking_for_orders(
                own_orders_ids, date_from=date_from.isoformat(),
                date_to=date_to.isoformat(), log_cb=log)
            for r in filtered:
                if r.order_id in tracking_map:
                    t = tracking_map[r.order_id]
                    r.tracking_number = t.get("tracking_number", "")
                    r.raw["_delivery_date"] = t.get("received_date") or ""
                    # Kurier: najpierw z formatu numeru przesylki (pewne),
                    # potem z nazwy pozycji wysylkowej Apilo (bywa "Shipping ...")
                    guessed = self._guess_courier_from_tracking(r.tracking_number)
                    if guessed:
                        r.courier = guessed
                    courier = r.courier.upper() if r.courier != "UNKNOWN" else ""
                    if r.tracking_number and courier:
                        r.tracking_url = self._build_tracking_url(courier, r.tracking_number)
            log(f"Znaleziono tracking dla {len(tracking_map)}/{len(own_orders_ids)} zamowien")

        total = len(filtered)
        # Folder per zamowienie
        order_folders: dict[str, Path] = {}
        for order in filtered:
            folder = kontrola_dir / order.order_number
            # wyczysc pozostalosci z poprzednich uruchomien (stare screenshoty/PDF-y)
            if folder.exists():
                for old in folder.iterdir():
                    try:
                        if old.is_file():
                            old.unlink()
                    except Exception:
                        pass
            folder.mkdir(parents=True, exist_ok=True)
            order_folders[order.order_id] = folder
            # usun tez stary gotowy PDF z DO_WYDRUKU — jesli zamowienie tym razem
            # zostanie pominiete, nie moze zostac nieaktualny plik do druku
            try:
                (print_dir / f"{self._safe_filename(order.order_number)}.pdf").unlink()
            except FileNotFoundError:
                pass
            except Exception:
                pass

        # Plan dowodu per zamowienie:
        #  - OWN z potwierdzona dostawa (received_date) -> screenshot trackingu
        #  - OWN bez potwierdzonej dostawy -> Amazon + Apilo
        #  - FBA -> Amazon + Apilo
        #  - faktura Amazon: FBA zawsze; FBM/OWN gdy brak faktury PL w Apilo
        def _delivered(o: OrderRecord) -> bool:
            return bool(o.raw.get("_delivery_date"))

        # Sprawdz z gory, ktore zamowienia maja fakture PL w Apilo
        apilo_has_pl: dict[str, bool] = {}
        if self.config.download_pl_invoices:
            log("Sprawdzanie faktur w Apilo...")
            for o in filtered:
                try:
                    docs = self.client.fetch_order_documents(o.order_id)
                except Exception:
                    docs = []
                apilo_has_pl[o.order_id] = any(
                    d.get("type") == 2 or is_pl_invoice_number(str(d.get("number") or ""))
                    for d in docs
                )

        plan: dict[str, dict[str, bool]] = {}
        for o in filtered:
            fba = o.warehouse_type == "fba"
            deliv = _delivered(o)
            has_track_url = bool(o.tracking_url and o.tracking_url.startswith("http"))
            # Tylko PRAWDZIWE zamowienia Amazon (format XXX-XXXXXXX-XXXXXXX).
            # eBay/inne platformy tez maja idExternal — nie wolno ich slac do Amazona.
            is_amazon = is_amazon_order_number(o.amazon_order_number)
            amazon_eu = is_amazon and o.country_code.upper() not in NA_COUNTRIES
            # Plan = to, czego WYMAGAMY do kompletu. Wylaczony checkbox (capture_*)
            # oznacza, ze danego dowodu swiadomie nie zbieramy — nie moze byc brakiem.
            plan[o.order_id] = {
                "tracking": (not fba) and deliv and has_track_url,
                "amazon": (fba or (not fba and not deliv)) and is_amazon
                          and self.config.capture_amazon,
                "apilo": (fba or (not fba and not deliv)) and self.config.capture_apilo_panel,
                # faktury Amazon tylko z panelu EU (USA: faktury sa w Apilo)
                "amazon_invoice": (self.config.download_pl_invoices and amazon_eu
                                   and (fba or not apilo_has_pl.get(o.order_id, False))),
            }

        tracking_shot_paths: dict[str, Path] = {}
        amazon_shot_paths: dict[str, Path] = {}
        apilo_shot_paths: dict[str, Path] = {}

        # === FAZA A: screenshoty trackingu kuriera (OWN z potwierdzona dostawa) ===
        track_orders = [o for o in filtered if plan[o.order_id]["tracking"]]
        for idx, order in enumerate(track_orders, start=1):
            log(f"[A {idx}/{len(track_orders)}] Tracking kuriera: {order.courier} {order.tracking_number}")
            try:
                shot = capture_tracking_screenshot(
                    tracking_url=order.tracking_url,
                    output_path=order_folders[order.order_id] / f"{order.order_number}_tracking.png",
                    config=self.config,
                    carrier=order.courier,
                )
                if shot:
                    tracking_shot_paths[order.order_id] = shot
            except Exception as exc:
                log(f"[A {idx}] Tracking nie powiodl sie: {exc}")

        # === FAZA B: Amazon — screenshoty + faktury PL (Deemed supply) ===
        amazon_invoice_paths: dict[str, list[Path]] = {}
        amazon_pl_found: dict[str, bool] = {}
        amazon_orders = [o for o in filtered
                         if plan[o.order_id]["amazon"] or plan[o.order_id]["amazon_invoice"]]
        if self.config.capture_amazon and amazon_orders:
            if has_session(self.config, "amazon"):
                log(f"Amazon (screenshoty/faktury): {len(amazon_orders)} zamowien...")
                sess = None
                try:
                    sess = CaptureSession("amazon", self.config, headless=False)
                    sess.__enter__()
                    for i, order in enumerate(amazon_orders, 1):
                        if i > 1:
                            time.sleep(2)  # lagodniejsze tempo — Amazon degraduje przy salwach
                        url = build_amazon_order_url(order.amazon_order_number, self.config,
                                                     country_code=order.country_code)
                        log(f"[Amazon {i}/{len(amazon_orders)}] {order.amazon_order_number} ({order.country_code})")
                        if sess.login_blocked:
                            log("Amazon: sesja wygasla i nie zalogowano — pozostale zamowienia "
                                "bez dowodow z Amazona (beda w DO_KONTROLI). Kliknij 'Zaloguj do "
                                "Amazon EU/USA', zaloguj sie i uruchom ponownie te zamowienia.")
                            break
                        # Blad JEDNEGO zamowienia nie moze zabic calej fazy
                        try:
                            if plan[order.order_id]["amazon"]:
                                out = sess.capture(url, order_folders[order.order_id] / f"{order.order_number}_amazon.png",
                                                   wait_ms=4000,
                                                   wait_for_text=order.amazon_order_number,
                                                   log_cb=log)
                                if out:
                                    amazon_shot_paths[order.order_id] = out
                            if plan[order.order_id]["amazon_invoice"]:
                                invs, has_pl = download_amazon_pl_invoices(
                                    sess, url, order_folders[order.order_id],
                                    order.amazon_order_number, log_cb=log)
                                amazon_invoice_paths[order.order_id] = invs
                                amazon_pl_found[order.order_id] = has_pl
                        except Exception as exc:
                            log(f"[Amazon {i}] blad: {str(exc)[:160]}")
                            if self._browser_dead(exc):
                                log("  Przegladarka Amazon padla/zostala zamknieta — otwieram ponownie...")
                                sess = self._restart_session(sess, "amazon", log)
                                if sess is None:
                                    break
                except Exception as exc:
                    log(f"Sesja Amazon nie powiodla sie: {exc}")
                finally:
                    if sess is not None:
                        sess.__exit__(None, None, None)
            else:
                log("UWAGA: brak sesji Amazon — kliknij 'Zaloguj do Amazon'.")

        # === FAZA C: screenshoty panelu Apilo (karta zamowienia) ===
        apilo_orders = [o for o in filtered if plan[o.order_id]["apilo"]]
        if self.config.capture_apilo_panel and apilo_orders:
            if self.config.apilo_panel_url and has_session(self.config, "apilo"):
                log(f"Screenshoty panelu Apilo: {len(apilo_orders)} zamowien...")
                sess = None
                try:
                    sess = CaptureSession("apilo", self.config, headless=False)
                    sess.__enter__()
                    for i, order in enumerate(apilo_orders, 1):
                        url = build_apilo_order_url(order.order_id, self.config)
                        log(f"[Apilo {i}/{len(apilo_orders)}] {order.order_id}")
                        if sess.login_blocked:
                            log("Apilo: sesja panelu wygasla i nie zalogowano — pozostale zamowienia "
                                "bez screenshotu Apilo (beda w DO_KONTROLI). Kliknij 'Zaloguj do "
                                "panelu Apilo' i uruchom ponownie te zamowienia.")
                            break
                        try:
                            out = sess.capture_cropped(
                                url, order_folders[order.order_id] / f"{order.order_number}_apilo.png",
                                bottom_text="Wiadomości i załączniki",
                                top_text=order.order_id,
                                wait_for_text=order.order_id,
                                wait_ms=4000, log_cb=log)
                            if out:
                                apilo_shot_paths[order.order_id] = out
                        except Exception as exc:
                            log(f"[Apilo {i}] blad: {str(exc)[:160]}")
                            if self._browser_dead(exc):
                                log("  Przegladarka Apilo padla/zostala zamknieta — otwieram ponownie...")
                                sess = self._restart_session(sess, "apilo", log)
                                if sess is None:
                                    break
                except Exception as exc:
                    log(f"Sesja Apilo nie powiodla sie: {exc}")
                finally:
                    if sess is not None:
                        sess.__exit__(None, None, None)
            else:
                log("UWAGA: brak sesji/URL panelu Apilo — pomijam screenshoty panelu.")

        # === FAZA D: faktury PL + skladanie PDF per zamowienie ===
        processed: list[ProcessingResult] = []
        for idx, order in enumerate(filtered, start=1):
            if progress_cb:
                progress_cb(idx, total)
            result = ProcessingResult(order=order, status="processing")
            folder = order_folders[order.order_id]
            try:
                # Filtr FBA: zamowienie kwalifikuje sie tylko z faktura PL w Amazon.
                # Pomijamy TYLKO przy definitywnym False (modal otwarty, PL brak).
                # None = nie udalo sie sprawdzic -> NIE pomijamy (trafi do niekompletnych).
                fba_no_pl = (order.warehouse_type == "fba"
                             and amazon_pl_found.get(order.order_id) is False)

                # Lista screenshotow (kolejnosc: Amazon, Apilo, tracking)
                shots: list[Path] = []
                if order.order_id in amazon_shot_paths:
                    shots.append(amazon_shot_paths[order.order_id])
                if order.order_id in apilo_shot_paths:
                    shots.append(apilo_shot_paths[order.order_id])
                if order.order_id in tracking_shot_paths:
                    shots.append(tracking_shot_paths[order.order_id])

                # Faktury: Apilo (OWN) + Amazon (FBA)
                invoice_pdfs: list[Path] = []
                if self.config.download_pl_invoices:
                    apilo_inv = self._download_pl_invoice(order, folder, idx, total, log)
                    if apilo_inv:
                        invoice_pdfs.append(apilo_inv)
                invoice_pdfs.extend(amazon_invoice_paths.get(order.order_id, []))

                # KOMPLET DOWODOW wg planu — tylko komplet trafia do DO_WYDRUKU.
                # Wszystko z brakami laduje w DO_KONTROLI/{nr}/ z plikiem BRAKI.txt.
                p = plan[order.order_id]
                missing: list[str] = []
                if p["tracking"] and order.order_id not in tracking_shot_paths:
                    missing.append("brak screenshota trackingu kuriera")
                if p["amazon"] and order.order_id not in amazon_shot_paths:
                    missing.append("brak screenshota zamowienia w Amazon")
                if p["apilo"] and order.order_id not in apilo_shot_paths:
                    missing.append("brak screenshota panelu Apilo")
                if self.config.download_pl_invoices and not invoice_pdfs:
                    missing.append("brak faktury PL (ani z Apilo, ani z Amazon)")
                if fba_no_pl:
                    missing.append("FBA bez faktury PL w Amazon (Deemed supply z innym "
                                   "prefiksem, np. FR/IT/DE) — pomijane zgodnie z ustaleniem")

                cover = generate_order_pdf(
                    order=order,
                    screenshots=shots,
                    output_path=folder / "_cover.pdf",
                    company_name=self.config.pdf_company_name,
                )
                safe = self._safe_filename(order.order_number)
                if not missing:
                    pdf = merge_pdfs(cover, invoice_pdfs, print_dir / f"{safe}.pdf")
                else:
                    pdf = merge_pdfs(cover, invoice_pdfs, folder / f"{safe}_NIEKOMPLETNY.pdf")
                    try:
                        (folder / "BRAKI.txt").write_text(
                            f"Zamowienie {order.order_number} — NIEKOMPLETNY zestaw dowodow:\n"
                            + "".join(f"  - {m}\n" for m in missing),
                            encoding="utf-8")
                    except Exception:
                        pass
                try:
                    Path(folder / "_cover.pdf").unlink()
                except Exception:
                    pass

                result.pdf_path = pdf
                result.screenshot_path = shots[0] if shots else None
                result.missing = missing
                if fba_no_pl:
                    result.status = "pominieto"
                    result.message = "Brak faktury PL w Amazon (Deemed supply)"
                    log(f"[D {idx}/{total}] POMINIETO {order.order_number}: brak faktury PL w Amazon")
                elif missing:
                    result.status = "niekompletne"
                    result.message = "; ".join(missing)
                    log(f"[D {idx}/{total}] NIEKOMPLETNE {order.order_number}: {result.message}")
                else:
                    result.status = "ok"
                    result.message = "OK"
                    log(f"[D {idx}/{total}] OK {order.order_number}")
            except Exception as exc:
                result.status = "error"
                result.message = str(exc)
                log(f"[D {idx}/{total}] BLAD {order.order_number}: {exc}")
            processed.append(result)

        ok_orders = [r.order for r in processed if r.status == "ok"]
        own_orders = [o for o in ok_orders if o.warehouse_type != "fba"]
        fba_orders = [o for o in ok_orders if o.warehouse_type == "fba"]

        summary_pdf = generate_summary_pdf(
            own_orders=own_orders,
            fba_orders=fba_orders,
            output_path=print_dir / "podsumowanie.pdf",
            company_name=self.config.pdf_company_name,
        )
        summary_xlsx = export_summary_xlsx(ok_orders, print_dir / "podsumowanie.xlsx")

        # Raport brakow: jedno spojrzenie na wszystko, co NIE poszlo do druku,
        # plus gotowa lista numerow do wklejenia w 'Numery Apilo' przy powtorce.
        from datetime import datetime as _dt
        problems = [r for r in processed if r.status in ("niekompletne", "pominieto", "error")]
        stamp = _dt.now().strftime("%Y-%m-%d_%H-%M")
        report = kontrola_dir / f"_RAPORT_BRAKOW_{stamp}.txt"
        try:
            lines = [
                f"RAPORT BRAKOW — uruchomienie {stamp}, zakres {date_from} - {date_to}",
                f"Kompletne (DO_WYDRUKU): {len(ok_orders)}",
                f"Niekompletne: {len([r for r in problems if r.status == 'niekompletne'])}",
                f"Pominiete (FBA bez faktury PL): {len([r for r in problems if r.status == 'pominieto'])}",
                f"Bledy: {len([r for r in problems if r.status == 'error'])}",
                "",
            ]
            for r in problems:
                lines.append(f"[{r.status.upper()}] {r.order.order_number}"
                             f"  (Amazon: {r.order.amazon_order_number or '-'}, {r.order.country_code})")
                for m in (r.missing or [r.message]):
                    lines.append(f"    - {m}")
            retry = [r.order.order_number for r in problems if r.status in ("niekompletne", "error")]
            if retry:
                lines += ["", "Do powtorki (wklej w pole 'Numery Apilo'):", ", ".join(retry)]
            report.write_text("\n".join(lines) + "\n", encoding="utf-8")
            log(f"Raport brakow: {report}")
        except Exception as exc:
            log(f"Nie udalo sie zapisac raportu brakow: {exc}")

        log(f"Zakończono. Wyniki: {output_dir}")
        return PipelineOutput(
            output_dir=output_dir,
            processed=processed,
            summary_pdf=summary_pdf,
            summary_xlsx=summary_xlsx,
        )
