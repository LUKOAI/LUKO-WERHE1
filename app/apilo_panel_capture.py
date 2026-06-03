from __future__ import annotations

from app.config import AppConfig


def build_apilo_order_url(order_id: str, config: AppConfig) -> str:
    """Buduje URL strony zamowienia w panelu www Apilo.

    Wzorzec do potwierdzenia na zywo z klientem. Typowe formaty:
      https://{konto}.apilo.com/zamowienia/{order_id}
      https://{konto}.apilo.com/orders/{order_id}
    """
    panel = config.apilo_panel_url.rstrip("/")
    return f"{panel}/zamowienia/{order_id}"
