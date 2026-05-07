from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models import OrderRecord



def generate_order_pdf(order: OrderRecord, screenshot_path: Path, output_path: Path, company_name: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4

    c.setTitle(f"{order.order_number}_{order.invoice_number}")

    # Nagłówek
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, height - 20 * mm, f"{company_name} - Dokument podatkowy")

    c.setStrokeColor(colors.black)
    c.line(20 * mm, height - 22 * mm, width - 20 * mm, height - 22 * mm)

    c.setFont("Helvetica", 10)
    y = height - 30 * mm
    lines = [
        f"Numer zamówienia: {order.order_number}",
        f"ID: {order.order_id}",
        f"Numer Amazon: {order.amazon_order_number or '-'}",
        f"Data zamówienia: {order.order_date.strftime('%Y-%m-%d %H:%M')}",
        f"Numer faktury: {order.invoice_number}",
        f"Kurier: {order.courier}",
        f"Tracking: {order.tracking_number}",
        f"Kraj dostawy: {order.country_code}",
        f"Adres: {order.customer_name}, {order.address_line_1} {order.address_line_2}, {order.postal_code} {order.city}",
        f"Wartość brutto: {order.total_gross:.2f} {order.currency}",
    ]
    for line in lines:
        c.drawString(20 * mm, y, line)
        y -= 5 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y - 2 * mm, "Potwierdzenie doręczenia (screenshot trackingu):")

    image_top = y - 8 * mm
    image_left = 20 * mm
    image_width = width - 40 * mm
    image_height = 130 * mm

    image = ImageReader(str(screenshot_path))
    iw, ih = image.getSize()
    scale = min(image_width / iw, image_height / ih)
    draw_w, draw_h = iw * scale, ih * scale

    c.rect(image_left, image_top - draw_h, image_width, image_height, stroke=1, fill=0)
    c.drawImage(image, image_left + (image_width - draw_w) / 2, image_top - draw_h, draw_w, draw_h)

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(20 * mm, 10 * mm, "Wygenerowano automatycznie przez narzędzie WERHE/WERKON.")
    c.save()

    return output_path



def generate_summary_pdf(
    own_orders: list[OrderRecord],
    fba_orders: list[OrderRecord],
    output_path: Path,
    company_name: str,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, height - 20 * mm, f"{company_name} - Podsumowanie miesięczne")

    c.setFont("Helvetica", 10)
    y = height - 30 * mm
    c.drawString(20 * mm, y, f"Liczba zamówień (magazyn własny): {len(own_orders)}")
    y -= 5 * mm
    c.drawString(20 * mm, y, f"Liczba zamówień (FBA/FBC): {len(fba_orders)}")
    y -= 8 * mm

    def draw_table(title: str, orders: list[OrderRecord], y_pos: float) -> float:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y_pos, title)
        y_pos -= 6 * mm

        c.setFont("Helvetica-Bold", 8)
        c.drawString(20 * mm, y_pos, "Nr zamówienia")
        c.drawString(60 * mm, y_pos, "Data")
        c.drawString(90 * mm, y_pos, "Kraj")
        c.drawString(105 * mm, y_pos, "Kurier")
        c.drawString(135 * mm, y_pos, "Faktura")
        y_pos -= 4 * mm
        c.line(20 * mm, y_pos, width - 20 * mm, y_pos)
        y_pos -= 4 * mm

        c.setFont("Helvetica", 8)
        for order in orders[:40]:
            c.drawString(20 * mm, y_pos, order.order_number[:24])
            c.drawString(60 * mm, y_pos, order.order_date.strftime("%Y-%m-%d"))
            c.drawString(90 * mm, y_pos, order.country_code)
            c.drawString(105 * mm, y_pos, order.courier[:18])
            c.drawString(135 * mm, y_pos, order.invoice_number[:22])
            y_pos -= 4.5 * mm
            if y_pos < 20 * mm:
                c.showPage()
                y_pos = height - 20 * mm
        return y_pos - 5 * mm

    y = draw_table("Magazyn własny", own_orders, y)
    if y < 80 * mm:
        c.showPage()
        y = height - 20 * mm
    draw_table("Amazon FBA/FBC", fba_orders, y)

    c.save()
    return output_path
