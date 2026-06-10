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
    """Tworzy strone(y) ze screenshotami — kazdy na pelna szerokosc, bez pomniejszania.

    Wysoki screenshot (np. karta Apilo) jest dzielony na kolejne strony A4
    w skali natywnej (zamiast sciskac do polowy strony).
    screenshots: lista sciezek (kolejnosc: amazon, apilo, tracking).
    """
    from PIL import Image
    import math

    if isinstance(screenshots, (str, Path)):
        screenshots = [screenshots]
    shots = [Path(s) for s in (screenshots or []) if s and Path(s).exists()]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4
    c.setTitle(f"{order.amazon_order_number or order.order_number}")

    margin = 8 * mm
    avail_w = width - 2 * margin
    avail_h = height - 2 * margin
    temp_files: list[Path] = []
    first_page = True

    if not shots:
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
        c.drawString(20 * mm, y - 6 * mm, "Brak screenshota potwierdzenia dostawy.")
        c.save()
        return output_path

    for shot in shots:
        try:
            img = Image.open(shot)
            iw, ih = img.size
        except Exception:
            continue
        scale = avail_w / iw
        scaled_h = ih * scale
        if scaled_h <= avail_h:
            # miesci sie na jednej stronie — pelna szerokosc
            if not first_page:
                c.showPage()
            first_page = False
            draw_h = scaled_h
            c.drawImage(str(shot), margin, height - margin - draw_h, avail_w, draw_h)
        else:
            # wysoki obraz — dziel na kolejne strony A4 w skali natywnej
            slice_src_h = int(iw * avail_h / avail_w)  # px zrodla na jedna pelna strone
            n = math.ceil(ih / slice_src_h)
            for i in range(n):
                if not first_page:
                    c.showPage()
                first_page = False
                top = i * slice_src_h
                bottom = min(ih, top + slice_src_h)
                crop = img.crop((0, top, iw, bottom))
                tmp = shot.with_name(f"{shot.stem}_p{i}.png")
                crop.save(tmp)
                temp_files.append(tmp)
                ch = (bottom - top) * scale
                c.drawImage(str(tmp), margin, height - margin - ch, avail_w, ch)

    c.save()
    for t in temp_files:
        try:
            t.unlink()
        except Exception:
            pass
    return output_path


def merge_pdfs(cover_pdf: Path, invoice_pdfs, output_path: Path) -> Path:
    """Laczy strone(y) ze screenshotami z faktura(mi) w jeden PDF.

    Kolejnosc: najpierw screenshot(y), potem strony kolejnych faktur.
    invoice_pdfs: pojedyncza sciezka, lista sciezek lub None.
    """
    if invoice_pdfs is None:
        invoice_pdfs = []
    if isinstance(invoice_pdfs, (str, Path)):
        invoice_pdfs = [invoice_pdfs]
    invoices = [Path(p) for p in invoice_pdfs if p and Path(p).exists()]

    if not invoices:
        if cover_pdf != output_path:
            Path(cover_pdf).replace(output_path)
        return output_path
    try:
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        for src in [cover_pdf, *invoices]:
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
