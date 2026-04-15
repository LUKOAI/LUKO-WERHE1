from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from app.config import AppConfig
from app.models import OrderRecord


class ApiloClientError(Exception):
    pass


class ApiloClient:
    """Klient REST API Apilo.

    Uwaga: pola mapowania mogą się różnić między kontami/integracjami, dlatego
    klucze są pobierane defensywnie i mają fallbacki.
    """

    def __init__(self, config: AppConfig, timeout: int = 30) -> None:
        self.config = config
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.apilo_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _url(self, endpoint: str) -> str:
        return self.config.apilo_base_url.rstrip("/") + "/" + endpoint.lstrip("/")

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        url = self._url(endpoint)
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ApiloClientError(f"Błąd API {method} {url}: {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise ApiloClientError(f"Nieprawidłowy JSON z {url}") from exc

    def fetch_orders(self, date_from: str, date_to: str) -> list[dict[str, Any]]:
        params = {"date_from": date_from, "date_to": date_to, "limit": 100, "page": 1}
        all_orders: list[dict[str, Any]] = []

        while True:
            payload = self._request("GET", self.config.apilo_orders_endpoint, params=params)
            chunk = payload.get("orders") or payload.get("data") or []
            if not isinstance(chunk, list):
                raise ApiloClientError("Odpowiedź API nie zawiera listy zamówień.")

            all_orders.extend(chunk)

            # Prosta paginacja - działająca dla typowych API.
            next_page = payload.get("next_page")
            has_more = payload.get("has_more")
            if next_page:
                params["page"] = next_page
            elif has_more:
                params["page"] += 1
            else:
                break

            if not chunk:
                break

        return all_orders

    def fetch_order_details(self, order_id: str) -> dict[str, Any]:
        endpoint = self.config.apilo_order_details_endpoint.format(order_id=order_id)
        payload = self._request("GET", endpoint)
        return payload.get("order") or payload.get("data") or payload

    @staticmethod
    def _parse_date(value: str | None) -> datetime:
        if not value:
            return datetime.utcnow()
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return datetime.utcnow()

    def to_order_record(self, raw: dict[str, Any], details: dict[str, Any] | None = None) -> OrderRecord:
        src = {**raw, **(details or {})}
        address = src.get("shipping_address") or src.get("delivery_address") or {}
        tracking = src.get("tracking") or {}
        invoice = src.get("invoice") or {}

        return OrderRecord(
            order_id=str(src.get("id") or src.get("order_id") or ""),
            order_number=str(src.get("order_number") or src.get("number") or "BRAK"),
            amazon_order_number=str(
                src.get("amazon_order_number")
                or src.get("amazon_order_id")
                or src.get("marketplace_order_id")
                or src.get("channel_order_id")
                or ""
            ),
            order_date=self._parse_date(src.get("created_at") or src.get("order_date")),
            country_code=(address.get("country_code") or src.get("country_code") or "").upper(),
            customer_name=address.get("name") or src.get("customer_name") or "",
            address_line_1=address.get("line1") or address.get("street") or "",
            address_line_2=address.get("line2") or "",
            city=address.get("city") or "",
            postal_code=address.get("postal_code") or address.get("zip") or "",
            courier=str(tracking.get("carrier") or src.get("courier") or "UNKNOWN"),
            tracking_number=str(tracking.get("number") or src.get("tracking_number") or ""),
            tracking_url=str(tracking.get("url") or src.get("tracking_url") or ""),
            invoice_number=str(invoice.get("number") or src.get("invoice_number") or ""),
            invoice_url=str(invoice.get("url") or src.get("invoice_url") or ""),
            warehouse_type=str(src.get("warehouse_type") or src.get("fulfillment") or "own").lower(),
            currency=str(src.get("currency") or "PLN"),
            total_gross=float(src.get("total_gross") or src.get("total") or 0.0),
            raw=src,
        )
