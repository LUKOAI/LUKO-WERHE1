from __future__ import annotations

from app.config import AppConfig

# Kraje obslugiwane przez Amazon Seller Central Ameryki Polnocnej (.com),
# reszta (UK, EU, eksport CH/NO itd.) przez panel europejski.
NA_COUNTRIES = {"US", "CA", "MX", "BR"}


def amazon_domain_for_country(country_code: str, config: AppConfig) -> str:
    cc = (country_code or "").upper()
    if cc in NA_COUNTRIES:
        return config.amazon_seller_domain_na
    return config.amazon_seller_domain


def build_amazon_order_url(amazon_order_number: str, config: AppConfig,
                           country_code: str = "") -> str:
    """Buduje URL strony zamowienia w Amazon Seller Central.

    Domena zalezy od kraju dostawy:
      US/CA/MX/BR -> sellercentral.amazon.com (Ameryka Polnocna)
      reszta (UK/EU/eksport) -> sellercentral-europe.amazon.com
    Wzorzec sciezki potwierdzony: /orders-v3/order/{numer}
    """
    domain = amazon_domain_for_country(country_code, config).rstrip("/")
    return f"https://{domain}/orders-v3/order/{amazon_order_number}"
