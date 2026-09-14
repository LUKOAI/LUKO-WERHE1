"""Instrukcja użytkowania LUKO AmaFakt (PDF) – prosta, dla osoby w biurze.

Użycie: python tools/make_user_guide.py [WYJSCIE.pdf]   (wymaga: pip install reportlab)
Domyślnie zapisuje output/LUKO-AmaFakt-instrukcja-uzytkownika.pdf
"""
from __future__ import annotations

import glob
import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from amazon_vat_merger import APP_NAME, AUTHOR, COPYRIGHT_YEAR, SUPPORT_EMAIL, __version__  # noqa: E402

# ---------- czcionki (polskie znaki) ----------
def _font(name: str) -> str | None:
    hits = glob.glob(f"/usr/share/fonts/**/{name}", recursive=True) + glob.glob(f"C:/Windows/Fonts/{name}")
    return hits[0] if hits else None


REG, BOLD = _font("DejaVuSans.ttf"), _font("DejaVuSans-Bold.ttf")
if REG and BOLD:
    pdfmetrics.registerFont(TTFont("Body", REG))
    pdfmetrics.registerFont(TTFont("Body-Bold", BOLD))
    pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body", boldItalic="Body-Bold")
    F, FB = "Body", "Body-Bold"
else:  # awaryjnie – bez polskich znaków w czcionkach wbudowanych może być krzywo
    F, FB = "Helvetica", "Helvetica-Bold"

NAVY = colors.HexColor("#1F3A5F")
ORANGE = colors.HexColor("#F28C28")
LIGHT = colors.HexColor("#F3F6FA")
GREY = colors.HexColor("#666666")
LINE = colors.HexColor("#D5DCE5")

S = {
    "title": ParagraphStyle("title", fontName=FB, fontSize=24, leading=30, textColor=NAVY),
    "subtitle": ParagraphStyle("subtitle", fontName=F, fontSize=12, leading=16, textColor=GREY),
    "h1": ParagraphStyle("h1", fontName=FB, fontSize=15, leading=20, textColor=colors.white, spaceBefore=0),
    "h2": ParagraphStyle("h2", fontName=FB, fontSize=11.5, leading=15, textColor=NAVY, spaceBefore=8, spaceAfter=3),
    "body": ParagraphStyle("body", fontName=F, fontSize=10.5, leading=15, alignment=TA_LEFT, spaceAfter=4),
    "small": ParagraphStyle("small", fontName=F, fontSize=9, leading=12, textColor=GREY),
    "step_no": ParagraphStyle("step_no", fontName=FB, fontSize=16, leading=18, textColor=colors.white),
    "step": ParagraphStyle("step", fontName=F, fontSize=10.5, leading=15),
    "cell": ParagraphStyle("cell", fontName=F, fontSize=9.5, leading=13),
    "cellb": ParagraphStyle("cellb", fontName=FB, fontSize=9.5, leading=13, textColor=NAVY),
    "tip": ParagraphStyle("tip", fontName=F, fontSize=10, leading=14, textColor=NAVY),
}


def P(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, S[style])


def heading(num: str, text: str) -> Table:
    """Pasek nagłówka rozdziału: granatowy z pomarańczowym numerem."""
    t = Table([[Paragraph(num, ParagraphStyle("hn", fontName=FB, fontSize=15, leading=20, textColor=ORANGE)),
                Paragraph(text, S["h1"])]], colWidths=[1.1 * cm, 15.9 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 8), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def steps(items: list[str]) -> Table:
    """Ponumerowane kroki: pomarańczowe kółko z numerem + tekst."""
    rows = [[Paragraph(str(i), S["step_no"]), Paragraph(txt, S["step"])] for i, txt in enumerate(items, start=1)]
    t = Table(rows, colWidths=[1.0 * cm, 16.0 * cm])
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINE),
    ]
    for r in range(len(rows)):
        style += [("BACKGROUND", (0, r), (0, r), ORANGE), ("ALIGN", (0, r), (0, r), "CENTER")]
    t.setStyle(TableStyle(style))
    return t


def tip(text: str, label: str = "Wskazówka") -> Table:
    t = Table([[Paragraph(f"<b>{label}:</b> {text}", S["tip"])]], colWidths=[17.0 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("LINEBEFORE", (0, 0), (0, -1), 3, ORANGE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def table(header: list[str], rows: list[list[str]], widths: list[float]) -> Table:
    data = [[Paragraph(h, S["cellb"]) for h in header]] + [[Paragraph(c, S["cell"]) for c in r] for r in rows]
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("LINEBELOW", (0, 0), (-1, 0), 1, NAVY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(F, 8)
    canvas.setFillColor(GREY)
    canvas.drawString(2 * cm, 1.2 * cm, f"{APP_NAME} v{__version__}  ·  © {COPYRIGHT_YEAR} {AUTHOR}  ·  pomoc i awarie: {SUPPORT_EMAIL}")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"strona {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(2 * cm, 1.6 * cm, A4[0] - 2 * cm, 1.6 * cm)
    canvas.restoreState()


def build(out: Path) -> Path:
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2.2 * cm,
                            title=f"{APP_NAME} – instrukcja użytkowania", author=AUTHOR, subject="Faktury Amazon i raport VAT w jednym arkuszu")
    st: list = []

    # ---------- strona tytułowa (nagłówek) ----------
    icon = ROOT / "assets" / "icon.png"
    head_left = [P(f"{APP_NAME}", "title"), P("Instrukcja użytkowania dla biura", "subtitle"),
                 P(f"wersja programu {__version__} · instrukcja z {date.today():%d.%m.%Y}", "small")]
    if icon.exists():
        t = Table([[Image(str(icon), 2.2 * cm, 2.2 * cm), head_left]], colWidths=[2.8 * cm, 14.2 * cm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (0, 0), 0)]))
        st.append(t)
    else:
        st += head_left
    st.append(Spacer(1, 10))
    st.append(tip("Program bierze <b>raport z Amazon (plik CSV)</b> i <b>faktury Amazon (pliki PDF)</b>, łączy je "
                  "i zapisuje gotowy <b>arkusz Google</b> oraz plik Excel. Ty tylko wskazujesz pliki i klikasz <b>Uruchom</b>. "
                  "Całość trwa około minuty.", "W skrócie"))
    st.append(Spacer(1, 12))

    # ---------- 1. co miesiąc ----------
    sec = [heading("1", "Co przygotować (raz w miesiącu, ok. 10 minut)"), Spacer(1, 6)]
    sec.append(steps([
        "Zaloguj się do <b>Amazon Seller Central</b>. Wejdź w <b>Reports → Tax Document Library</b>.",
        "Zakładka <b>Amazon VAT Transactions Report</b>: wybierz miesiąc → <b>Generate</b> → <b>Download</b>. "
        "Zapisz plik CSV do folderu <b>C:\\LUKO-AmaFakt\\raporty</b>.",
        "W tej samej bibliotece pobierz <b>faktury i noty kredytowe</b> (pliki PDF) za ten miesiąc. "
        "Zapisz je do folderu <b>C:\\LUKO-AmaFakt\\faktury</b> – najlepiej w podfolderze z nazwą miesiąca, np. <b>2026-09</b>.",
    ]))
    sec.append(Spacer(1, 6))
    sec.append(tip("Nazwy plików PDF to numery faktur (np. <b>PL600IIBG6O6HU.pdf</b>). Program sam dopasowuje każdą fakturę "
                   "do wiersza raportu po tym numerze – nie trzeba niczego przepisywać ani zmieniać nazw."))
    st.append(KeepTogether(sec))
    st.append(Spacer(1, 12))

    # ---------- 2. uruchomienie ----------
    sec = [heading("2", "Uruchomienie (2 minuty)"), Spacer(1, 6)]
    sec.append(steps([
        "Kliknij dwa razy ikonę <b>LUKO AmaFakt</b> na pulpicie (pomarańczowa ikona z literą A). "
        "Otworzy się okno z sześcioma polami i przyciskiem <b>Uruchom</b>.",
        "<b>Raport CSV</b>: kliknij <b>Wybierz…</b> i zaznacz raport za ten miesiąc. Można zaznaczyć kilka plików naraz.",
        "<b>Folder z fakturami PDF</b>: wskaż folder z fakturami za ten miesiąc (np. <b>C:\\LUKO-AmaFakt\\faktury\\2026-09</b>).",
        "Pozostałe pola (<b>Folder na wyniki</b>, <b>ID arkusza Google</b>, <b>Klucz konta serwisowego</b>) "
        "są zapamiętane z poprzedniego razu – nie zmieniaj ich.",
        "Kliknij <b>Uruchom</b>. W dolnej części okna przewija się dziennik pracy. Poczekaj na linię zaczynającą się od "
        "<b>GOTOWE</b> i na status <b>Zakończono</b> obok przycisków.",
        "Otwórz arkusz Google w przeglądarce – zakładki są już zapisane. Ten sam wynik jako plik Excel otworzysz "
        "przyciskiem <b>Otwórz wynik</b>.",
    ]))
    st.append(KeepTogether(sec))
    st.append(Spacer(1, 12))

    # ---------- 3. co powstaje ----------
    sec = [heading("3", "Co dostajesz po uruchomieniu"), Spacer(1, 6),
           P("Arkusz Google (ten sam za każdym razem – program nadpisuje w nim swoje zakładki):", "h2")]
    sec.append(table(["Zakładka", "Co zawiera"], [
        ["<b>Wszystko</b>", "Każda transakcja z raportu w jednym wierszu: dane z raportu Amazon + dane z faktury PDF "
                            "(kupujący, adres, kwoty, kurs NBP, przeliczenie na PLN). Kolumna A to link – kliknięcie "
                            "przenosi do tej faktury w zakładce kraju."],
        ["<b>DE OSS, FR Lokalna, PL WDT…</b>", "Po jednej zakładce na kraj i rodzaj sprzedaży, w układzie takim jak "
                                                "dotychczasowy arkusz księgowy. Wiersz 1: kraj i rodzaj, wiersz 2: nagłówki, "
                                                "od wiersza 4 dane, na końcu wiersz RAZEM z sumami."],
        ["<b>DE OSS KOREKTA</b> itd.", "Zwroty i noty kredytowe (kwoty ujemne) – osobno od sprzedaży, dla każdego kraju i rodzaju. "
                                        "Zakładka powstaje sama, gdy w danym miesiącu są korekty."],
        ["<b>Diagnostyka</b>", "Lista rzeczy do sprawdzenia: transakcje bez faktury PDF, różnice kwot między fakturą a raportem, "
                               "brak kursu waluty. Pierwszy wiersz: wersja programu, data wygenerowania, nazwa raportu."],
    ], [4.2, 12.8]))
    sec.append(Spacer(1, 8))
    sec.append(P("Folder wyników (C:\\LUKO-AmaFakt\\wyniki):", "h2"))
    sec.append(table(["Plik", "Do czego służy"], [
        ["<b>amazon_vat_RRRRMMDD_GGMMSS.xlsx</b>", "Ten sam arkusz jako plik Excel – kopia na dysku, do wysłania mailem lub do "
                                                    "ręcznego importu do Google (Plik → Importuj), gdyby połączenie z Google nie działało."],
        ["<b>faktury.json</b>", "To, co program odczytał z faktur PDF. Przydaje się przy zgłaszaniu problemu."],
        ["<b>luko-amafakt.log</b>", "Pełny dziennik pracy ze szczegółami technicznymi. Przy problemie wystarczy wysłać ten plik."],
    ], [5.2, 11.8]))
    sec.append(Spacer(1, 8))
    sec.append(tip("Każde uruchomienie zapisuje tylko to, co wskażesz – dane się nie sumują z poprzednimi miesiącami. "
                   "Zakładka z poprzedniego miesiąca, dla której teraz nie ma danych (np. KOREKTA), zostaje wyczyszczona "
                   "i dostaje notatkę z datą. Twoje własne zakładki o innych nazwach program zostawia w spokoju.", "Ważne"))
    st.append(KeepTogether(sec))
    st.append(Spacer(1, 12))

    # ---------- 4. diagnostyka ----------
    sec = [heading("4", "Zakładka Diagnostyka – co sprawdzić"), Spacer(1, 6)]
    sec.append(table(["Wpis", "Co to znaczy i co zrobić"], [
        ["<b>Brak PDF</b>", "Transakcja jest w raporcie, ale nie ma jej faktury w folderze. Dograj brakujący PDF do folderu "
                            "i kliknij <b>Uruchom</b> jeszcze raz."],
        ["<b>PDF bez transakcji w CSV</b>", "Faktura jest w folderze, ale nie ma jej w raporcie – zwykle faktura z innego miesiąca. "
                                             "Nic nie trzeba robić."],
        ["<b>Kwota PDF ≠ CSV</b>", "Suma na fakturze różni się od raportu. Warto sprawdzić tę fakturę ręcznie."],
        ["<b>Brak kursu PLN</b>", "Nie udało się pobrać kursu z NBP (brak internetu?). Uruchom ponownie, gdy połączenie wróci – "
                                  "kolumny w PLN się uzupełnią."],
        ["<b>Nota do faktury spoza raportu</b>", "Nota kredytowa dotyczy faktury z wcześniejszego miesiąca. To normalne."],
    ], [4.6, 12.4]))
    st.append(KeepTogether(sec))
    st.append(Spacer(1, 12))

    # ---------- 5. komunikaty ----------
    sec = [heading("5", "Komunikaty w oknie programu"), Spacer(1, 6)]
    sec.append(table(["Co widzisz", "Co zrobić"], [
        ["<b>GOTOWE: transakcje: 120 | dopasowane: 118 | bez PDF: 2 …</b>", "Wszystko poszło dobrze. Liczba „bez PDF” to faktury do dogrania (patrz Diagnostyka)."],
        ["<b>Zakończono – błąd Google Sheets</b>", "Plik Excel jest gotowy, ale arkusz Google nie został zapisany. Powód jest "
                                                    "w dzienniku – najczęściej jeden z dwóch poniższych."],
        ["<b>brak dostępu do arkusza … udostępnij arkusz adresowi … jako Edytor</b>",
         "Arkusz Google nie jest udostępniony kontu programu albo ma tylko rolę „Przeglądający”. W arkuszu: <b>Udostępnij</b> → "
         "wpisz podany adres → rola <b>Edytor</b>."],
        ["<b>nie znaleziono arkusza o ID …</b>", "W polu <b>ID arkusza Google</b> jest zły ciąg znaków. Skopiuj go z adresu arkusza "
                                                  "(fragment między <b>/d/</b> a <b>/edit</b>)."],
        ["<b>API NBP niedostępne</b>", "Komputer nie ma połączenia z internetem albo zapora blokuje api.nbp.pl. Kolumny w PLN "
                                       "będą puste – uruchom ponownie, gdy połączenie wróci."],
        ["<b>plik jest otwarty w innym programie (Excel)?</b>", "Zamknij poprzedni wynik w Excelu i kliknij <b>Uruchom</b> jeszcze raz."],
        ["<b>Nie wskazano folderu z fakturami PDF…</b>", "Zapomniano wskazać folder. Kliknij „Nie”, wskaż folder i uruchom ponownie."],
        ["Niebieskie okno Windows <b>„System Windows ochronił ten komputer”</b>",
         "Pojawia się tylko przy pierwszym uruchomieniu nowej wersji. Kliknij <b>Więcej informacji</b> → <b>Uruchom mimo to</b>."],
    ], [6.4, 10.6]))
    st.append(KeepTogether(sec))
    st.append(Spacer(1, 12))

    # ---------- 6. dobre nawyki ----------
    sec = [heading("6", "Dobre nawyki"), Spacer(1, 6)]
    sec.append(steps([
        "Zanim klikniesz <b>Uruchom</b>, zamknij poprzedni wynik, jeśli jest otwarty w Excelu.",
        "Nie uruchamiaj programu w tym samym czasie na dwóch komputerach – oba piszą do tego samego arkusza Google.",
        "Jeden miesiąc = jeden raport CSV i jeden podfolder z fakturami. Program działa wtedy szybciej, a Diagnostyka jest czytelna.",
        "Nie zmieniaj nazw zakładek utworzonych przez program (np. „DE OSS”) – przy kolejnym uruchomieniu powstałyby drugie.",
        "Własne notatki i obliczenia trzymaj w osobnych zakładkach o innych nazwach – program ich nie dotyka.",
        "Po dograniu brakujących faktur po prostu uruchom program jeszcze raz – nadpisze wszystko poprawnie.",
        "Nowa wersja programu = podmiana jednego pliku <b>LUKO-AmaFakt.exe</b> w folderze C:\\LUKO-AmaFakt. Ustawienia zostają.",
    ]))
    st.append(KeepTogether(sec))
    st.append(Spacer(1, 14))

    # ---------- 7. pomoc ----------
    st.append(KeepTogether([
        heading("7", "Gdy coś nie działa – pomoc"),
        Spacer(1, 6),
        P(f"Napisz na <b>{SUPPORT_EMAIL}</b> (adres jest też na dole okna programu – kliknięcie otwiera nowy e-mail). Dołącz:", "body"),
        steps([
            "plik <b>luko-amafakt.log</b> z folderu wyników,",
            "plik <b>faktury.json</b> z tego samego folderu,",
            "numer wersji z dołu okna programu (np. <b>v" + __version__ + "</b>) i jedno zdanie, co się wydarzyło.",
        ]),
        Spacer(1, 6),
        P("Nie trzeba wysyłać faktur PDF ani raportu. Uwaga: faktury.json zawiera dane kupujących odczytane z faktur "
          "(nazwiska, adresy) – wysyłaj go wyłącznie na podany adres pomocy.", "small"),
    ]))

    doc.build(st, onFirstPage=footer, onLaterPages=footer)
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "output" / "LUKO-AmaFakt-instrukcja-uzytkownika.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"zapisano {build(target)}")
