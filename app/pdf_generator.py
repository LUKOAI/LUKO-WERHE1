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


def _draw_image_fit(c, img_path: Path, x: float, y_top: float, max_w: float, max_h: float) -> float:
    """Rysuje obraz dopasowany do (max_w x max_h) zaczynajac od gornego y. Zwraca dolny y."""
    image = ImageReader(str(img_path))
    iw, ih = image.getSize()
    scale = min(max_w / iw, max_h / ih)
    draw_w, draw_h = iw * scale, ih * scale
    img_y = y_top - draw_h
    c.rect(x, img_y, draw_w, draw_h, stroke=1, fill=0)
    c.drawImage(image, x, img_y, draw_w, draw_h)
    return img_y


def generate_order_pdf(order: OrderRecord, screenshots, output_path: Path,
                       company_name: str) -> Path:
    """Tworzy strone(y) ze screenshotami.

    screenshots: lista sciezek do PNG (np. [amazon, apilo] albo [tracking]).
    - 2 obrazy → jedna strona A4, ulozone jeden pod drugim (Amazon gora, Apilo dol).
    - 1 obraz → jedna strona A4 z naglowkiem danych zamowienia.
    """
    if isinstance(screenshots, (str, Path)):
        screenshots = [screenshots]
    shots = [Path(s) for s in (screenshots or []) if s and Path(s).exists()]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4
    c.setTitle(f"{order.amazon_order_number or order.order_number}")

    if len(shots) >= 2:
        # Dwa obrazy na jednej A4 (Amazon + Apilo)
        margin = 12 * mm
        gap = 6 * mm
        usable_w = width - 2 * margin
        half_h = (height - 2 * margin - gap) / 2
        top1 = height - margin
        bottom1 = _draw_image_fit(c, shots[0], margin, top1, usable_w, half_h)
        top2 = bottom1 - gap
        # gdyby pierwszy zajal mniej, drugi i tak w dolnej polowie
        top2 = min(top2, margin + half_h)
        _draw_image_fit(c, shots[1], margin, top2, usable_w, half_h)
    elif len(shots) == 1:
        # Jeden obraz + krotki naglowek danych
        c.setFont(FONT, 10)
        y = height - 20 * mm
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
        c.drawString(20 * mm, y, "Potwierdzenie doręczenia:")
        y -= 8 * mm
        _draw_image_fit(c, shots[0], 20 * mm, y, width - 40 * mm, y - 20 * mm)
    else:
        # Brak screenshota — same dane
        c.setFont(FONT, 10)
        y = height - 20 * mm
        for line in [
            f"Numer Amazon: {order.amazon_order_number or '-'}",
            f"Data zamówienia: {order.order_date.strftime('%Y-%m-%d %H:%M')}",
            f"Kurier: {order.courier}",
            f"Numer przesyłki: {order.tracking_number or 'brak danych'}",
            f"Kraj dostawy: {order.country_code}",
            f"Adres: {order.customer_name}, {order.address_line_1} {order.address_line_2}, {order.postal_code} {order.city}",
        ]:
            c.drawString(20 * mm, y, line)
            y -= 5 * mm
        c.setFont(FONT, 10)
        c.drawString(20 * mm, y - 6 * mm, "Brak screenshota potwierdzenia dostawy.")

    c.setFont(FONT, 8)
    c.drawString(20 * mm, 8 * mm, "Wygenerowano automatycznie przez narzędzie WERHE/WERKON.")
    c.save()
    return output_path


def merge_pdfs(cover_pdf: Path, invoice_pdf: Path | None, output_path: Path) -> Path:
    """Laczy strone(y) ze screenshotami z faktura (wielostronicowa) w jeden PDF.

    Kolejnosc: najpierw screenshot(y), potem strony faktury.
    Jesli brak faktury — zwraca sam cover.
    """
    if not invoice_pdf or not Path(invoice_pdf).exists():
        if cover_pdf != output_path:
            Path(cover_pdf).replace(output_path)
        return output_path
    try:
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        for src in (cover_pdf, invoice_pdf):
            reader = PdfReader(str(src))
            for page in reader.pages:
                writer.add_page(page)
        with open(output_path, "wb") as fh:
            writer.write(fh)
        return output_path
    except Exception:
        # fallback: zostaw sam cover
        if cover_pdf != output_path:
            Path(cover_pdf).replace(output_path)
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
        c.drawString(20 * mm, y_pos, "Klient")
        c.drawString(65 * mm, y_pos, "Adres")
        c.drawString(135 * mm, y_pos, "Data wysyłki")
        c.drawString(165 * mm, y_pos, "Data doręczenia")
        y_pos -= 4 * mm
        c.line(20 * mm, y_pos, width - 20 * mm, y_pos)
        y_pos -= 4 * mm

        c.setFont(FONT, 7)
        for order in orders:
            addr = f"{order.address_line_1}, {order.postal_code} {order.city}"
            send_date = (order.raw.get("sendDateMin") or "")[:10]
            c.drawString(20 * mm, y_pos, order.customer_name[:28])
            c.drawString(65 * mm, y_pos, addr[:42])
            c.drawString(135 * mm, y_pos, send_date)
            c.drawString(165 * mm, y_pos, "")
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
