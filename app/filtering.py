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



def prefilter_non_eu(order: OrderRecord) -> bool:
    """Wstepny filtr — tylko kraj (dane z listy nie zawieraja tracking/invoice)."""
    return bool(order.country_code) and is_non_eu(order.country_code)


def qualifies_for_tax_bundle(order: OrderRecord) -> bool:
    """Pelny filtr — po wzbogaceniu danymi ze szczegółów zamówienia."""
    if not is_non_eu(order.country_code):
        return False
    # Tracking i faktura opcjonalne jesli brak danych z API
    has_tracking = bool(order.tracking_url or order.tracking_number)
    has_invoice = bool(order.invoice_number) and has_pl_invoice(order)
    # Jesli mamy fakture .pl — kwalifikuje sie (tracking moze byc pobrany osobno)
    # Jesli nie mamy danych o fakturze — tez przepuszczamy (API moze nie zwracac)
    if has_invoice:
        return True
    if not order.invoice_number:
        return True
    return False
