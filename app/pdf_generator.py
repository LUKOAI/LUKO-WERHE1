from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.models import OrderRecord


def _register_polish_font() -> tuple[str, str]:
    candidates = [
        ("Arial", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("Calibri", "C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
        ("Segoe", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
        ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for name, regular, bold in candidates:
        try:
            if Path(regular).exists():
                pdfmetrics.registerFont(TTFont(name, regular))
                if Path(bold).exists():
                    pdfmetrics.registerFont(TTFont(name + "-Bold", bold))
                    return name, name + "-Bold"
                return name, name
        except Exception:
            continue
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = _register_polish_font()


def generate_order_pdf(order: OrderRecord, screenshot_path: Path | None, output_path: Path, company_name: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4

    c.setTitle(f"{order.amazon_order_number or order.order_number}")

    c.setFont(FONT_BOLD, 14)
    c.drawString(20 * mm, height - 20 * mm, f"{company_name} - Dokument podatkowy")

    c.setStrokeColor(colors.black)
    c.line(20 * mm, height - 22 * mm, width - 20 * mm, height - 22 * mm)

    c.setFont(FONT, 10)
    y = height - 30 * mm
    lines = [
        f"Numer Amazon: {order.amazon_order_number or '-'}",
        f"Data zamówienia: {order.order_date.strftime('%Y-%m-%d %H:%M')}",
        f"Kurier: {order.courier}",
        f"Numer przesyłki: {order.tracking_number or 'brak danych'}",
        f"Kraj dostawy: {order.country_code}",
        f"Adres: {order.customer_name}, {order.address_line_1} {order.address_line_2}, {order.postal_code} {order.city}",
    ]
    for line in lines:
        c.drawString(20 * mm, y, line)
        y -= 5 * mm

    y -= 3 * mm
    c.setFont(FONT_BOLD, 11)
    c.drawString(20 * mm, y, "Potwierdzenie doręczenia (screenshot trackingu):")
    y -= 8 * mm

    if screenshot_path and screenshot_path.exists():
        image = ImageReader(str(screenshot_path))
        iw, ih = image.getSize()
        image_width = width - 40 * mm
        image_max_h = y - 20 * mm
        scale = min(image_width / iw, image_max_h / ih)
        draw_w, draw_h = iw * scale, ih * scale
        img_y = y - draw_h
        c.rect(20 * mm, img_y, draw_w, draw_h, stroke=1, fill=0)
        c.drawImage(image, 20 * mm, img_y, draw_w, draw_h)
    else:
        c.setFont(FONT, 10)
        c.drawString(20 * mm, y - 4 * mm, "Brak screenshota trackingu - tracking URL niedostępny w danych API.")
        if order.tracking_number:
            c.drawString(20 * mm, y - 10 * mm, f"Numer przesyłki: {order.tracking_number}")
        if order.tracking_url:
            c.drawString(20 * mm, y - 16 * mm, f"URL: {order.tracking_url}")

    c.setFont(FONT, 8)
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

    c.setFont(FONT_BOLD, 14)
    c.drawString(20 * mm, height - 20 * mm, f"{company_name} - Podsumowanie miesięczne")

    c.setFont(FONT, 10)
    y = height - 30 * mm
    c.drawString(20 * mm, y, f"Liczba zamówień (magazyn własny): {len(own_orders)}")
    y -= 5 * mm
    c.drawString(20 * mm, y, f"Liczba zamówień (FBA/FBC): {len(fba_orders)}")
    y -= 8 * mm

    def draw_table(title: str, orders: list[OrderRecord], y_pos: float) -> float:
        c.setFont(FONT_BOLD, 11)
        c.drawString(20 * mm, y_pos, title)
        y_pos -= 6 * mm

        c.setFont(FONT_BOLD, 8)
        c.drawString(20 * mm, y_pos, "Nr Amazon")
        c.drawString(60 * mm, y_pos, "Data")
        c.drawString(85 * mm, y_pos, "Kraj")
        c.drawString(100 * mm, y_pos, "Kurier")
        c.drawString(125 * mm, y_pos, "Nr przesyłki")
        c.drawString(170 * mm, y_pos, "Typ")
        y_pos -= 4 * mm
        c.line(20 * mm, y_pos, width - 20 * mm, y_pos)
        y_pos -= 4 * mm

        c.setFont(FONT, 7)
        for order in orders:
            c.drawString(20 * mm, y_pos, (order.amazon_order_number or "-")[:24])
            c.drawString(60 * mm, y_pos, order.order_date.strftime("%Y-%m-%d"))
            c.drawString(85 * mm, y_pos, order.country_code)
            c.drawString(100 * mm, y_pos, order.courier[:18])
            c.drawString(125 * mm, y_pos, (order.tracking_number or "-")[:24])
            c.drawString(170 * mm, y_pos, order.warehouse_type.upper())
            y_pos -= 4 * mm
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
