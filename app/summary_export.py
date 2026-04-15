from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from app.models import OrderRecord



def export_summary_xlsx(orders: list[OrderRecord], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Podsumowanie"

    ws.append(
        [
            "order_id",
            "order_number",
            "amazon_order_number",
            "order_date",
            "country_code",
            "customer_name",
            "city",
            "courier",
            "tracking_number",
            "invoice_number",
            "warehouse_type",
            "total_gross",
            "currency",
        ]
    )

    for o in orders:
        ws.append(
            [
                o.order_id,
                o.order_number,
                o.amazon_order_number,
                o.order_date.strftime("%Y-%m-%d %H:%M:%S"),
                o.country_code,
                o.customer_name,
                o.city,
                o.courier,
                o.tracking_number,
                o.invoice_number,
                o.warehouse_type,
                o.total_gross,
                o.currency,
            ]
        )

    wb.save(output_path)
    return output_path
