from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from app.apilo_client import ApiloClient
from app.apilo_auth import ensure_valid_token
from app.config import AppConfig
from app.filtering import prefilter_non_eu, qualifies_for_tax_bundle
from app.models import OrderRecord, ProcessingResult
from app.pdf_generator import generate_order_pdf, generate_summary_pdf
from app.summary_export import export_summary_xlsx
from app.tracking_capture import capture_tracking_screenshot


ProgressCallback = Callable[[int, int], None]
LogCallback = Callable[[str], None]


@dataclass
class PipelineOutput:
    output_dir: Path
    processed: list[ProcessingResult]
    summary_pdf: Path
    summary_xlsx: Path


TRACKING_URLS = {
    "UPS": "https://www.ups.com/track?loc=en_PL&tracknum={tn}",
    "DPD": "https://tracktrace.dpd.com.pl/parcelDetails?typ=1&p1={tn}",
    "DHL": "https://www.dhl.com/pl-en/home/tracking.html?tracking-id={tn}",
    "FEDEX": "https://www.fedex.com/fedextrack/?trknbr={tn}",
    "GLS": "https://gls-group.com/PL/pl/sledzenie-paczek?match={tn}",
    "INPOST": "https://inpost.pl/sledzenie-przesylek?number={tn}",
    "POCZTA": "https://emonitoring.poczta-polska.pl/?numer={tn}",
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

        # Krok 4: Wyszukanie numerów tracking w shipmentach Apilo
        own_orders_ids = {r.order_id for r in filtered if r.warehouse_type != "fba"}
        if own_orders_ids:
            log(f"Szukanie trackingu dla {len(own_orders_ids)} zamowien (magazyn wlasny)...")
            tracking_map = self.client.fetch_tracking_for_orders(own_orders_ids, log_cb=log)
            for r in filtered:
                if r.order_id in tracking_map:
                    t = tracking_map[r.order_id]
                    r.tracking_number = t.get("tracking_number", "")
                    courier = r.courier.upper() if r.courier != "UNKNOWN" else ""
                    if r.tracking_number and courier:
                        r.tracking_url = self._build_tracking_url(courier, r.tracking_number)
            log(f"Znaleziono tracking dla {len(tracking_map)}/{len(own_orders_ids)} zamowien")

        apilo_query = {v.strip().lower() for v in (selected_apilo_numbers or set()) if v.strip()}
        amazon_query = {v.strip().lower() for v in (selected_amazon_numbers or set()) if v.strip()}

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

        processed: list[ProcessingResult] = []
        total = len(filtered)

        for idx, order in enumerate(filtered, start=1):
            if progress_cb:
                progress_cb(idx, total)
            result = ProcessingResult(order=order, status="processing")
            try:
                shot = None
                if order.tracking_url and order.tracking_url.startswith("http"):
                    log(f"[{idx}/{total}] Screenshot trackingu: {order.tracking_url[:60]}...")
                    shot = capture_tracking_screenshot(
                        tracking_url=order.tracking_url,
                        output_path=shots_dir / f"{order.order_number}_tracking.png",
                        config=self.config,
                        carrier=order.courier,
                    )
                    result.screenshot_path = shot
                elif order.tracking_number:
                    log(f"[{idx}/{total}] Brak URL trackingu, numer: {order.tracking_number}")
                else:
                    log(f"[{idx}/{total}] Brak danych trackingowych")

                pdf = generate_order_pdf(
                    order=order,
                    screenshot_path=shot,
                    output_path=order_pdf_dir / f"{order.order_number}.pdf",
                    company_name=self.config.pdf_company_name,
                )
                result.pdf_path = pdf
                result.status = "ok"
                result.message = "OK"
                log(f"[{idx}/{total}] OK {order.order_number}")
            except Exception as exc:
                result.status = "error"
                result.message = str(exc)
                log(f"[{idx}/{total}] BLAD {order.order_number}: {exc}")
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
