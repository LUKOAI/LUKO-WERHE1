"""Amazon VAT merger – łączy raport VAT Transactions (CSV) z fakturami VCS (PDF)
i buduje arkusz (xlsx / Google Sheets) ze wszystkimi danymi."""

APP_NAME = "LUKO AmaFakt"
APP_SLUG = "LUKO-AmaFakt"
__version__ = "0.2.2"

AUTHOR = "Netanaliza"
SUPPORT_EMAIL = "support@netanaliza.com"
COPYRIGHT_YEAR = 2026


def about_line() -> str:
    """Jedna linia: nazwa, wersja, prawa autorskie, kontakt (okienko, zakładka Diagnostyka, --version)."""
    return f"{APP_NAME} v{__version__} · © {COPYRIGHT_YEAR} {AUTHOR} · pomoc i awarie: {SUPPORT_EMAIL}"
