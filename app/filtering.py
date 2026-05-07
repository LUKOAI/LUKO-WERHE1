from __future__ import annotations

from app.models import OrderRecord

EU_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",
}

# Waluty krajow UE (do heurystyki gdy brak country)
EU_CURRENCIES = {
    "PLN", "EUR", "CZK", "HUF", "RON", "BGN", "SEK", "DKK", "HRK",
}

# Waluty jednoznacznie poza UE
NON_EU_CURRENCIES = {
    "USD", "GBP", "CHF", "NOK", "JPY", "CAD", "AUD", "NZD", "TRY", "ILS",
    "BRL", "MXN", "KRW", "TWD", "SGD", "HKD", "INR", "ZAR", "AED", "SAR",
}


def is_non_eu(country_code: str) -> bool:
    if not country_code:
        return False
    return country_code.upper() not in EU_COUNTRIES


def has_pl_invoice(order: OrderRecord) -> bool:
    invoice_ref = (order.invoice_url or order.invoice_number or "").lower().strip()
    return invoice_ref.endswith(".pl") or ".pl/" in invoice_ref


def _currency_suggests_non_eu(currency: str) -> bool:
    """Gdy brak kraju, waluta moze wskazywac na zamowienie poza UE."""
    if not currency:
        return False
    return currency.upper() in NON_EU_CURRENCIES


def prefilter_non_eu(order: OrderRecord) -> bool:
    """Wstepny filtr — kraj lub waluta wskazuje na poza UE."""
    if order.country_code:
        return is_non_eu(order.country_code)
    # Brak kraju — sprawdzamy walute
    return _currency_suggests_non_eu(order.currency)


def qualifies_for_tax_bundle(order: OrderRecord) -> bool:
    """Pelny filtr po wzbogaceniu danymi ze szczegolów."""
    # Jesli znamy kraj — sprawdzamy
    if order.country_code:
        if not is_non_eu(order.country_code):
            return False
    elif not _currency_suggests_non_eu(order.currency):
        # Brak kraju i waluta EU — odrzucamy
        return False

    if order.invoice_number and not has_pl_invoice(order):
        return False

    return True
