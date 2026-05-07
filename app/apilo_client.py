from __future__ import annotations

import logging
import time
from datetime import datetime
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

        address = (
            src.get("shipping_address")
            or src.get("delivery_address")
            or src.get("deliveryAddress")
            or src.get("address")
            or {}
        )

        tracking = src.get("tracking") or {}
        shipments = src.get("shipments") or src.get("shipment") or []
        if isinstance(shipments, list) and shipments:
            tracking = {**tracking, **shipments[0]}
        elif isinstance(shipments, dict):
            tracking = {**tracking, **shipments}

        invoice = src.get("invoice") or {}
        documents = src.get("documents") or src.get("invoices") or []
        if isinstance(documents, list) and documents:
            invoice = {**invoice, **documents[0]}

        return OrderRecord(
            order_id=str(src.get("id") or src.get("order_id") or src.get("orderId") or ""),
            order_number=str(
                src.get("order_number") or src.get("orderNumber")
                or src.get("number") or src.get("id") or "BRAK"
            ),
            amazon_order_number=str(
                src.get("amazon_order_number")
                or src.get("amazonOrderNumber")
                or src.get("amazon_order_id")
                or src.get("marketplace_order_id")
                or src.get("marketplaceOrderId")
                or src.get("channel_order_id")
                or src.get("externalId")
                or src.get("id_external")
                or ""
            ),
            order_date=self._parse_date(
                src.get("created_at") or src.get("createdAt")
                or src.get("order_date") or src.get("orderDate")
            ),
            country_code=(
                address.get("country_code") or address.get("countryCode")
                or address.get("country") or src.get("country_code") or ""
            ).upper(),
            customer_name=(
                address.get("name") or address.get("fullName")
                or src.get("customer_name") or src.get("customerName") or ""
            ),
            address_line_1=address.get("line1") or address.get("street") or address.get("address1") or "",
            address_line_2=address.get("line2") or address.get("address2") or "",
            city=address.get("city") or "",
            postal_code=address.get("postal_code") or address.get("postalCode") or address.get("zip") or "",
            courier=str(
                tracking.get("carrier") or tracking.get("carrierName")
                or tracking.get("courier") or src.get("courier") or "UNKNOWN"
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
            warehouse_type=str(
                src.get("warehouse_type") or src.get("warehouseType")
                or src.get("fulfillment") or src.get("fulfillmentType") or "own"
            ).lower(),
            currency=str(src.get("currency") or "PLN"),
            total_gross=float(src.get("total_gross") or src.get("totalGross") or src.get("total") or 0.0),
            raw=src,
        )
