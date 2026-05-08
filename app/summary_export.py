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
            "customer_name",
            "Data wysyłki",
            "Data doręczenia",
            "Ulica, kod pocztowy, miasto, stan",
        ]
    )

    for o in orders:
        send_date = (o.raw.get("sendDateMin") or o.raw.get("orderedAt") or "")[:10]
        delivery_date = (o.raw.get("_delivery_date") or "")[:10]
        parts = [o.address_line_1, o.postal_code, o.city, o.address_line_2]
        full_address = ", ".join(p for p in parts if p)

        ws.append(
            [
                o.customer_name,
                send_date,
                delivery_date,
                full_address,
            ]
        )

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    wb.save(output_path)
    return output_path
