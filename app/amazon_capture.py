from __future__ import annotations

from app.config import AppConfig


def build_amazon_order_url(amazon_order_number: str, config: AppConfig) -> str:
    """Buduje URL strony zamowienia w Amazon Seller Central.

    Wzorzec do potwierdzenia na zywo z klientem. Typowe formaty:
      https://sellercentral-europe.amazon.com/orders-v3/order/{id}
      https://sellercentral.amazon.de/orders-v3/order/{id}
    """
    domain = config.amazon_seller_domain.rstrip("/")
    return f"https://{domain}/orders-v3/order/{amazon_order_number}"
