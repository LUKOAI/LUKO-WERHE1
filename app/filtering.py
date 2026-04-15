from __future__ import annotations

from app.models import OrderRecord

EU_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",
}



def is_non_eu(country_code: str) -> bool:
    return country_code.upper() not in EU_COUNTRIES



def has_pl_invoice(order: OrderRecord) -> bool:
    """Faktura kwalifikuje się gdy kończy się na '.pl' (URL lub numer)."""
    invoice_ref = (order.invoice_url or order.invoice_number or "").lower().strip()
    return invoice_ref.endswith(".pl") or ".pl/" in invoice_ref



def qualifies_for_tax_bundle(order: OrderRecord) -> bool:
    return bool(order.tracking_url) and is_non_eu(order.country_code) and has_pl_invoice(order)
