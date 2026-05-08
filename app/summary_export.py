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
            "amazon_order_number",
            "order_date",
            "country_code",
            "customer_name",
            "city",
            "warehouse_type",
            "total_gross",
            "currency",
            "Data wysyłki",
            "Data doręczenia",
            "Ulica",
            "Kod pocztowy",
            "Miasto",
            "Stan",
        ]
    )

    for o in orders:
        ws.append(
            [
                o.amazon_order_number,
                o.order_date.strftime("%Y-%m-%d %H:%M:%S"),
                o.country_code,
                o.customer_name,
                o.city,
                o.warehouse_type,
                o.total_gross,
                o.currency,
                "",
                "",
                o.address_line_1,
                o.postal_code,
                o.city,
                o.address_line_2,
            ]
        )

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 30)

    wb.save(output_path)
    return output_path
