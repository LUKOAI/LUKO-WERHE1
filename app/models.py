from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class OrderRecord:
    """Ujednolicony model zamówienia używany w całej aplikacji."""

    order_id: str
    order_number: str
    amazon_order_number: str
    order_date: datetime
    country_code: str
    customer_name: str
    address_line_1: str
    address_line_2: str
    city: str
    postal_code: str
    courier: str
    tracking_number: str
    tracking_url: str
    invoice_number: str
    invoice_url: str
    warehouse_type: str  # "fba" lub "own"
    currency: str
    total_gross: float
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessingResult:
    """Wynik przetwarzania jednego zamówienia."""

    order: OrderRecord
    screenshot_path: Optional[Path] = None
    pdf_path: Optional[Path] = None
    status: str = "pending"
    message: str = ""
