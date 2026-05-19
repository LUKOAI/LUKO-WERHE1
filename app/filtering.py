from __future__ import annotations

from app.models import OrderRecord

EU_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",
}


def is_non_eu(country_code: str) -> bool:
    if not country_code:
        return False
    return country_code.upper() not in EU_COUNTRIES


def is_eu(country_code: str) -> bool:
    if not country_code:
        return False
    return country_code.upper() in EU_COUNTRIES


def has_pl_invoice(order: OrderRecord) -> bool:
    invoice_ref = (order.invoice_url or order.invoice_number or "").lower().strip()
    return invoice_ref.endswith(".pl") or ".pl/" in invoice_ref


def prefilter_non_eu(order: OrderRecord) -> bool:
    """Wstepny filtr — odrzuca TYLKO zamowienia ze ZNANYM krajem EU.
    Wszystko inne (poza EU lub brak kraju) → przepuszcza do weryfikacji.
    """
    if is_eu(order.country_code):
        return False
    return True


def qualifies_for_tax_bundle(order: OrderRecord) -> bool:
    """Pelny filtr po wzbogaceniu danymi ze szczegolów.
    Odrzuca tylko zamowienia z potwierdzonym krajem EU.
    Brak kraju → przepuszcza (lepiej miec za duzo niz stracic).
    """
    if is_eu(order.country_code):
        return False

    if order.invoice_number and not has_pl_invoice(order):
        return False

    return True
