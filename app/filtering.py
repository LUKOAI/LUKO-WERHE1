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


def has_pl_invoice(order: OrderRecord) -> bool:
    invoice_ref = (order.invoice_url or order.invoice_number or "").lower().strip()
    return invoice_ref.endswith(".pl") or ".pl/" in invoice_ref


def prefilter_non_eu(order: OrderRecord) -> bool:
    """Wstepny filtr na danych z listy (bez szczegolów).

    Logika:
    - Znany kraj EU → odrzuc
    - Znany kraj poza EU → przepusc
    - Brak kraju + PLN → odrzuc (prawdopodobnie krajowe)
    - Brak kraju + inna waluta → przepusc (trzeba sprawdzic szczegoly)
    """
    if order.country_code:
        return is_non_eu(order.country_code)
    # Brak kraju — PLN prawie na pewno krajowe
    if order.currency.upper() == "PLN":
        return False
    # Inna waluta (EUR, GBP, USD...) — moze byc poza UE, trzeba sprawdzic
    return True


def qualifies_for_tax_bundle(order: OrderRecord) -> bool:
    """Pelny filtr po wzbogaceniu danymi ze szczegolów."""
    if order.country_code:
        if not is_non_eu(order.country_code):
            return False
    else:
        # Nadal brak kraju po pobraniu szczegolów — nie mozemy potwierdzic
        return False

    if order.invoice_number and not has_pl_invoice(order):
        return False

    return True
