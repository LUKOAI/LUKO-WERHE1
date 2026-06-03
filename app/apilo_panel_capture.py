from __future__ import annotations

from app.config import AppConfig


def build_apilo_order_url(order_id: str, config: AppConfig) -> str:
    """Buduje URL strony zamowienia w panelu www Apilo.

    Potwierdzony wzorzec (z panelu klienta):
      https://{konto}.apilo.com/order/order/detail/{order_id}/
    """
    panel = config.apilo_panel_url.rstrip("/")
    return f"{panel}/order/order/detail/{order_id}/"
