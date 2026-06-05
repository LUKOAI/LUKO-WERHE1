from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from app.apilo_auth import ensure_valid_token
from app.config import AppConfig
from app.models import OrderRecord

logger = logging.getLogger("werhe_tool")

ORDERS_ENDPOINT = "/rest/api/orders/"
ORDER_DETAIL_ENDPOINT = "/rest/api/orders/{order_id}/"
STATUS_MAP_ENDPOINT = "/rest/api/orders/status-map/"
MAX_LIMIT = 512
MAX_RETRIES = 3


class ApiloClientError(Exception):
    pass


class ApiloClient:
    """Klient REST API Apilo — poprawna autentykacja OAuth, endpointy i paginacja offset/limit."""

    def __init__(self, config: AppConfig, timeout: int = 30) -> None:
        self.config = config
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._update_auth_header()

    def _update_auth_header(self) -> None:
        if self.config.apilo_access_token:
            self.session.headers["Authorization"] = f"Bearer {self.config.apilo_access_token}"

    def _url(self, endpoint: str) -> str:
        return self.config.apilo_base_url.rstrip("/") + "/" + endpoint.lstrip("/")

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        url = self._url(endpoint)

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)

                if response.status_code == 401 and attempt == 0:
                    logger.info("Token wygasł (401) — odświeżam...")
                    self.config = ensure_valid_token(self.config)
                    self._update_auth_header()
                    continue

                if response.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning("Rate limit (429) — czekam %ds...", wait)
                    time.sleep(wait)
                    continue

                response.raise_for_status()

            except requests.RequestException as exc:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise ApiloClientError(f"Błąd API {method} {url}: {exc}") from exc

            try:
                return response.json()
            except ValueError as exc:
                raise ApiloClientError(f"Nieprawidłowy JSON z {url}") from exc

        raise ApiloClientError(f"Przekroczono liczbę prób dla {method} {url}")

    def ensure_authenticated(self) -> None:
        self.config = ensure_valid_token(self.config)
        self._update_auth_header()

    def fetch_orders(self, date_from: str, date_to: str) -> list[dict[str, Any]]:
        all_orders: list[dict[str, Any]] = []
        offset = 0

        while True:
            params = {
                "createdAfter": f"{date_from}T00:00:00+00:00",
                "createdBefore": f"{date_to}T23:59:59+00:00",
                "limit": MAX_LIMIT,
                "offset": offset,
            }

            payload = self._request("GET", ORDERS_ENDPOINT, params=params)

            chunk = (
                payload.get("orders")
                or payload.get("data")
                or payload.get("items")
                or payload.get("results")
                or []
            )

            if isinstance(payload, list):
                chunk = payload

            if not isinstance(chunk, list):
                logger.warning("Nieoczekiwany format odpowiedzi: %s", type(chunk))
                break

            all_orders.extend(chunk)
            logger.info("Pobrano %d zamówień (offset=%d)", len(chunk), offset)

            if len(chunk) < MAX_LIMIT:
                break

            offset += len(chunk)

        return all_orders

    def fetch_order_details(self, order_id: str) -> dict[str, Any]:
        endpoint = ORDER_DETAIL_ENDPOINT.format(order_id=order_id)
        payload = self._request("GET", endpoint)
        return payload.get("order") or payload.get("data") or payload

    def fetch_order_documents(self, order_id: str) -> list[dict[str, Any]]:
        """Pobiera liste dokumentow (faktur) powiazanych z zamowieniem.

        GET /rest/api/orders/{order_id}/documents/
        Kazdy dokument ma m.in.: number, type, media (plik PDF).
        """
        endpoint = f"/rest/api/orders/{order_id}/documents/"
        try:
            payload = self._request("GET", endpoint)
        except ApiloClientError:
            return []
        docs = (
            payload.get("documents")
            or payload.get("data")
            or payload.get("items")
            or []
        )
        if isinstance(payload, list):
            docs = payload
        return docs if isinstance(docs, list) else []

    def fetch_document_detail(self, order_id: str, document_id) -> dict[str, Any]:
        """Szczegoly dokumentu — zawieraja pole 'media' (UUID pliku PDF)."""
        endpoint = f"/rest/api/orders/{order_id}/documents/{document_id}/"
        try:
            return self._request("GET", endpoint)
        except ApiloClientError:
            return {}

    def download_document_file(self, document: dict[str, Any], output_path: Path,
                               order_id: str | None = None) -> Path | None:
        """Pobiera plik PDF faktury.

        Lista dokumentow nie zawiera 'media' — pobieramy je ze szczegolow dokumentu,
        a nastepnie plik z GET /rest/api/media/{uuid}/ (potwierdzone na zywo).
        """
        media = document.get("media")
        if not media and order_id and document.get("id"):
            detail = self.fetch_document_detail(order_id, document.get("id"))
            media = detail.get("media")
        if not media:
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(media, dict):
            media = media.get("url") or media.get("id") or media.get("uuid") or ""
        media = str(media)
        if not media:
            return None

        if media.startswith("http"):
            url = media
        else:
            url = self.config.apilo_base_url.rstrip("/") + f"/rest/api/media/{media}/"

        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            output_path.write_bytes(resp.content)
            return output_path
        except requests.RequestException:
            return None

    TRACKING_ENDPOINT = "/rest/api/shipping/shipment/tracking/"
    SHIPMENT_DETAIL = "/rest/api/shipping/shipment/{sid}/"

    def _shipment_postdate(self, offset: int) -> tuple[str, Any]:
        """Zwraca (postDate 'YYYY-MM-DD', shipment_id) dla przesylki na danym offsecie."""
        page = self._request("GET", self.TRACKING_ENDPOINT, params={"offset": offset, "limit": 1})
        sh = page.get("shipments", [])
        if not sh:
            return "", None
        sid = sh[0].get("id")
        try:
            det = self._request("GET", self.SHIPMENT_DETAIL.format(sid=sid))
            pd = (det.get("postDate") or det.get("createdAt") or "")[:10]
            return pd, sid
        except Exception:
            return "", sid

    def fetch_tracking_for_orders(self, order_ids: set[str],
                                  date_from: str | None = None,
                                  date_to: str | None = None,
                                  log_cb=None) -> dict[str, dict[str, str]]:
        """Numer przesylki + data dostawy dla zamowien — skan po ZAKRESIE DAT.

        Lista przesylek jest posortowana rosnaco po dacie. Binary search znajduje
        poczatek miesiaca, potem skanujemy tylko ten zakres (i konczymy gdy znajdziemy
        wszystkie szukane zamowienia). Zwraca orderId -> {tracking_number, received_date, status}.
        """
        def log(msg):
            if log_cb:
                log_cb(msg)
            logger.info(msg)

        first = self._request("GET", self.TRACKING_ENDPOINT, params={"offset": 0, "limit": 1})
        total = first.get("totalCount", 0)
        if total == 0:
            return {}

        # Binary search: pierwszy offset gdzie postDate >= date_from
        start_offset = 0
        if date_from:
            lo, hi = 0, total - 1
            while lo <= hi:
                mid = (lo + hi) // 2
                pd, _ = self._shipment_postdate(mid)
                if not pd:
                    break
                if pd < date_from:
                    lo = mid + 1
                else:
                    start_offset = mid
                    hi = mid - 1
            # cofnij sie troche dla bezpieczenstwa (przesylka moze byc nadana pozniej niz zamowienie)
            start_offset = max(0, start_offset - 512)

        # gorna granica skanu = date_to + 14 dni (dostawa/nadanie po dacie zamowienia)
        stop_boundary = date_to
        if date_to:
            try:
                from datetime import datetime, timedelta
                stop_boundary = (datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=14)).strftime("%Y-%m-%d")
            except Exception:
                stop_boundary = date_to

        result: dict[str, dict[str, str]] = {}
        remaining = set(order_ids)
        log(f"Szukanie trackingu od pozycji {start_offset} (zakres {date_from} - {date_to})...")

        offset = start_offset
        scanned = 0
        MAX_SCAN = 6000  # bezpiecznik
        while offset < total and remaining and scanned < MAX_SCAN:
            batch = min(512, total - offset)
            page = self._request("GET", self.TRACKING_ENDPOINT, params={"offset": offset, "limit": batch})
            shipments = page.get("shipments", [])
            if not shipments:
                break
            stop = False
            for s in shipments:
                sid = s.get("id")
                if not sid:
                    continue
                try:
                    det = self._request("GET", self.SHIPMENT_DETAIL.format(sid=sid))
                except Exception:
                    continue
                scanned += 1
                pd = (det.get("postDate") or det.get("createdAt") or "")[:10]
                # przekroczylismy gorny zakres dat (+14 dni marginesu) -> stop
                if stop_boundary and pd and pd > stop_boundary:
                    stop = True
                    break
                oid = det.get("orderId", "")
                if oid in remaining:
                    result[oid] = {
                        "tracking_number": det.get("externalId") or s.get("externalId") or "",
                        "received_date": s.get("receivedDate") or "",
                        "status": s.get("statusDescription") or "",
                    }
                    remaining.discard(oid)
                    log(f"  Tracking {oid}: {result[oid]['tracking_number']} "
                        f"(dostawa: {result[oid]['received_date'] or 'brak'})")
            offset += len(shipments)
            log(f"  Przeskanowano {scanned} przesylek, znaleziono {len(result)}/{len(order_ids)}")
            if stop:
                break

        return result

    def get_status_map(self) -> dict[str, str]:
        try:
            payload = self._request("GET", STATUS_MAP_ENDPOINT)
            return payload.get("data") or payload
        except ApiloClientError:
            logger.warning("Nie udało się pobrać mapy statusów")
            return {}

    @staticmethod
    def _parse_date(value: str | None) -> datetime:
        if not value:
            return datetime.utcnow()
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return datetime.utcnow()

    def to_order_record(self, raw: dict[str, Any], details: dict[str, Any] | None = None) -> OrderRecord:
        src = {**raw, **(details or {})}

        # Apilo: addressCustomer (fakturowy), addressDelivery (dostawy)
        address = (
            src.get("addressDelivery")
            or src.get("addressCustomer")
            or src.get("shipping_address")
            or src.get("delivery_address")
            or {}
        )

        # Tracking z shipments lub bezpośrednio
        tracking = src.get("tracking") or {}
        shipments = src.get("shipments") or src.get("shipment") or []
        if isinstance(shipments, list) and shipments:
            tracking = {**tracking, **shipments[0]}
        elif isinstance(shipments, dict):
            tracking = {**tracking, **shipments}

        # Faktura z documents/invoices
        invoice = src.get("invoice") or {}
        documents = src.get("documents") or src.get("invoices") or []
        if isinstance(documents, list) and documents:
            invoice = {**invoice, **documents[0]}

        # Adres: Apilo używa streetName + streetNumber
        street = address.get("streetName") or address.get("street") or address.get("line1") or address.get("address1") or ""
        street_nr = address.get("streetNumber") or ""
        if street and street_nr:
            full_street = f"{street} {street_nr}"
        else:
            full_street = street

        # Kurier: z orderItems type=2 (pozycja wysylkowa) lub carrierId
        courier_name = ""
        if src.get("orderItems"):
            for item in src["orderItems"]:
                if item.get("type") == 2:
                    name = item.get("originalName") or ""
                    if name and name not in ("Shipping", "Wysyłka"):
                        courier_name = name.split(" ")[0].upper()
                    break

        # Kwota: sumuj z orderItems jeśli brak total
        total = src.get("total_gross") or src.get("totalGross") or src.get("total") or 0.0
        if not total and src.get("orderItems"):
            try:
                total = sum(
                    float(item.get("originalPriceWithTax") or 0) * int(item.get("quantity") or 1)
                    for item in src["orderItems"]
                    if item.get("type") == 1
                )
            except (ValueError, TypeError):
                total = 0.0

        return OrderRecord(
            order_id=str(src.get("id") or src.get("order_id") or ""),
            order_number=str(src.get("id") or src.get("order_number") or src.get("number") or "BRAK"),
            amazon_order_number=str(src.get("idExternal") or src.get("id_external") or ""),
            order_date=self._parse_date(src.get("createdAt") or src.get("created_at")),
            country_code=(
                address.get("country") or address.get("country_code") or address.get("countryCode") or ""
            ).upper(),
            customer_name=address.get("name") or address.get("fullName") or "",
            address_line_1=full_street,
            address_line_2=address.get("department") or address.get("line2") or "",
            city=address.get("city") or "",
            postal_code=address.get("zipCode") or address.get("postal_code") or address.get("zip") or "",
            courier=(
                courier_name
                or tracking.get("carrier") or tracking.get("carrierName")
                or tracking.get("courier") or str(src.get("carrierId") or "UNKNOWN")
            ),
            tracking_number=str(
                tracking.get("number") or tracking.get("trackingNumber")
                or src.get("tracking_number") or ""
            ),
            tracking_url=str(
                tracking.get("url") or tracking.get("trackingUrl")
                or src.get("tracking_url") or ""
            ),
            invoice_number=str(
                invoice.get("number") or invoice.get("invoiceNumber")
                or src.get("invoice_number") or ""
            ),
            invoice_url=str(
                invoice.get("url") or invoice.get("invoiceUrl")
                or src.get("invoice_url") or ""
            ),
            warehouse_type=self._detect_fulfillment(src),
            currency=str(src.get("originalCurrency") or src.get("currency") or "PLN"),
            total_gross=float(total),
            raw=src,
        )

    @staticmethod
    def _detect_fulfillment(src: dict[str, Any]) -> str:
        """FBA gdy brak carrierId i carrierAccount (Amazon realizuje wysylke)."""
        carrier_id = src.get("carrierId")
        carrier_account = src.get("carrierAccount")
        if carrier_id is None and carrier_account is None:
            return "fba"
        return "own"
