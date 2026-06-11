from __future__ import annotations

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
from app.amazon_capture import build_amazon_order_url, download_amazon_pl_invoices, NA_COUNTRIES
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
        shots_dir = output_dir / "_screenshots"
        order_pdf_dir = output_dir / "zamowienia"
        output_dir.mkdir(parents=True, exist_ok=True)
        shots_dir.mkdir(parents=True, exist_ok=True)
        order_pdf_dir.mkdir(parents=True, exist_ok=True)

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
                    courier = r.courier.upper() if r.courier != "UNKNOWN" else ""
                    if r.tracking_number and courier:
                        r.tracking_url = self._build_tracking_url(courier, r.tracking_number)
            log(f"Znaleziono tracking dla {len(tracking_map)}/{len(own_orders_ids)} zamowien")

        total = len(filtered)
        # Folder per zamowienie
        order_folders: dict[str, Path] = {}
        for order in filtered:
            folder = order_pdf_dir / order.order_number
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
            amazon_eu = bool(o.amazon_order_number) and o.country_code.upper() not in NA_COUNTRIES
            plan[o.order_id] = {
                "tracking": (not fba) and deliv and has_track_url,
                "amazon": (fba or (not fba and not deliv)) and bool(o.amazon_order_number),
                "apilo": fba or (not fba and not deliv),
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
                try:
                    with CaptureSession("amazon", self.config, headless=False) as sess:
                        for i, order in enumerate(amazon_orders, 1):
                            url = build_amazon_order_url(order.amazon_order_number, self.config,
                                                         country_code=order.country_code)
                            log(f"[Amazon {i}/{len(amazon_orders)}] {order.amazon_order_number} ({order.country_code})")
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
                    log(f"Sesja Amazon nie powiodla sie: {exc}")
            else:
                log("UWAGA: brak sesji Amazon — kliknij 'Zaloguj do Amazon'.")

        # === FAZA C: screenshoty panelu Apilo (karta zamowienia) ===
        apilo_orders = [o for o in filtered if plan[o.order_id]["apilo"]]
        if self.config.capture_apilo_panel and apilo_orders:
            if self.config.apilo_panel_url and has_session(self.config, "apilo"):
                log(f"Screenshoty panelu Apilo: {len(apilo_orders)} zamowien...")
                try:
                    with CaptureSession("apilo", self.config, headless=False) as sess:
                        for i, order in enumerate(apilo_orders, 1):
                            url = build_apilo_order_url(order.order_id, self.config)
                            log(f"[Apilo {i}/{len(apilo_orders)}] {order.order_id}")
                            out = sess.capture_cropped(
                                url, order_folders[order.order_id] / f"{order.order_number}_apilo.png",
                                bottom_text="Wiadomości i załączniki",
                                top_text=order.order_id,
                                wait_for_text=order.order_id,
                                wait_ms=4000, log_cb=log)
                            if out:
                                apilo_shot_paths[order.order_id] = out
                except Exception as exc:
                    log(f"Sesja Apilo nie powiodla sie: {exc}")
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
                # Pomijamy TYLKO gdy faktycznie sprawdzilismy modal i PL nie bylo.
                if (order.warehouse_type == "fba"
                        and order.order_id in amazon_pl_found
                        and not amazon_pl_found[order.order_id]):
                    result.status = "pominieto"
                    result.message = "Brak faktury PL w Amazon (Deemed supply)"
                    log(f"[D {idx}/{total}] POMINIETO {order.order_number}: brak faktury PL w Amazon")
                    processed.append(result)
                    continue

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

                cover = generate_order_pdf(
                    order=order,
                    screenshots=shots,
                    output_path=folder / "_cover.pdf",
                    company_name=self.config.pdf_company_name,
                )
                final_name = f"{self._safe_filename(order.order_number)}.pdf"
                pdf = merge_pdfs(cover, invoice_pdfs, folder / final_name)
                try:
                    Path(folder / "_cover.pdf").unlink()
                except Exception:
                    pass

                result.pdf_path = pdf
                result.screenshot_path = shots[0] if shots else None
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
            output_path=output_dir / "podsumowanie.pdf",
            company_name=self.config.pdf_company_name,
        )
        summary_xlsx = export_summary_xlsx(ok_orders, output_dir / "podsumowanie.xlsx")

        log(f"Zakończono. Wyniki: {output_dir}")
        return PipelineOutput(
            output_dir=output_dir,
            processed=processed,
            summary_pdf=summary_pdf,
            summary_xlsx=summary_xlsx,
        )
