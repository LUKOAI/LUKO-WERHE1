from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from app.config import AppConfig

# Kraje obslugiwane przez Amazon Seller Central Ameryki Polnocnej (.com),
# reszta (UK, EU, eksport CH/NO itd.) przez panel europejski.
NA_COUNTRIES = {"US", "CA", "MX", "BR"}

# Numer faktury PL Amazon (Deemed supply), np. PL600040G6O6HD, PL600005G6O6HR
PL_INVOICE_RE = re.compile(r"\bPL[A-Z0-9]{8,}\b")


def amazon_domain_for_country(country_code: str, config: AppConfig) -> str:
    cc = (country_code or "").upper()
    if cc in NA_COUNTRIES:
        return config.amazon_seller_domain_na
    return config.amazon_seller_domain


def build_amazon_order_url(amazon_order_number: str, config: AppConfig,
                           country_code: str = "") -> str:
    """Buduje URL strony zamowienia w Amazon Seller Central.

    Domena zalezy od kraju dostawy:
      US/CA/MX/BR -> sellercentral.amazon.com (Ameryka Polnocna)
      reszta (UK/EU/eksport) -> sellercentral-europe.amazon.com
    Wzorzec sciezki potwierdzony: /orders-v3/order/{numer}
    """
    domain = amazon_domain_for_country(country_code, config).rstrip("/")
    return f"https://{domain}/orders-v3/order/{amazon_order_number}"


def _find_download_button_near(page, number: str):
    """Znajduje przycisk Download w tym samym wierszu co numer faktury.

    Modal Amazona nie zawsze uzywa <tr> — dopasowujemy PO POZYCJI:
    bierzemy element z numerem i wybieramy przycisk/link 'Download'
    o najblizszej wspolrzednej pionowej (ten sam wiersz wizualny).
    """
    try:
        num_el = page.get_by_text(number, exact=False).first
        num_el.wait_for(timeout=8000)
        num_box = num_el.bounding_box()
        if not num_box:
            return None
        num_y = num_box["y"] + num_box["height"] / 2

        candidates = page.get_by_text("Download", exact=False)
        count = candidates.count()
        best, best_dist = None, 1e9
        for i in range(count):
            el = candidates.nth(i)
            try:
                box = el.bounding_box()
            except Exception:
                continue
            if not box:
                continue
            y = box["y"] + box["height"] / 2
            dist = abs(y - num_y)
            if dist < best_dist:
                best, best_dist = el, dist
        # przycisk musi byc w sensownej odleglosci (ten sam wiersz, max ~60px)
        if best is not None and best_dist <= 60:
            return best
        return best  # nawet jesli dalej — ostatnia szansa, kliknij najblizszy
    except Exception:
        return None


def _find_manage_invoice_button(page):
    """Szuka przycisku 'Manage invoice' kilkoma strategiami + JS fallback.

    Po wielu nawigacjach w jednej sesji Amazon SPA degraduje sie i Playwright
    nie znajduje przycisku standardowymi locatorami — JS querySelector dziala.
    """
    # Strategia 1-3: Playwright locatory
    strategies = [
        lambda: page.get_by_role("button", name=re.compile(r"manage invoices?", re.I)).first,
        lambda: page.get_by_text(re.compile(r"Manage invoices?", re.I)).first,
        lambda: page.locator("[id*='invoice' i], [class*='invoice' i]")
                    .get_by_text(re.compile("manage", re.I)).first,
    ]
    for make in strategies:
        try:
            el = make()
            el.wait_for(timeout=5000)
            el.scroll_into_view_if_needed(timeout=3000)
            return el
        except Exception:
            continue

    # Strategia 4: JavaScript querySelector (SPA moze miec elementy niedostepne dla locatorow)
    try:
        handle = page.evaluate_handle("""
            () => {
                const all = document.querySelectorAll('span, button, a, div');
                for (const el of all) {
                    const txt = (el.textContent || '').trim();
                    if (/^manage invoices?$/i.test(txt)) return el;
                }
                return null;
            }
        """)
        if handle and str(handle) != "JSHandle@null":
            return handle.as_element()
    except Exception:
        pass

    return None


def download_amazon_pl_invoices(sess, order_url: str, folder: Path,
                                amazon_order_number: str,
                                log_cb: Callable[[str], None] | None = None
                                ) -> tuple[list[Path], bool | None]:
    """Pobiera faktury PL (Deemed supply) z modala 'Manage invoice'.

    Przebieg (potwierdzony na screenshotach klienta):
      1. Strona zamowienia -> przycisk 'Manage invoice'
      2. Modal 'Invoices for order {nr}' z tabela: Date / Type / Number / Status / Action
      3. Wiersze z numerem PL... (typ 'Deemed supply') -> przycisk Download

    Zwraca (lista_pobranych_pdf, czy_jest_faktura_PL):
      True  = modal otwarty, faktura PL jest
      False = modal otwarty, faktury PL NIE ma (definitywne — mozna pominac FBA)
      None  = nie udalo sie sprawdzic (NIE pomijac zamowienia!)
    """
    def log(m: str) -> None:
        if log_cb:
            log_cb(m)

    downloaded: list[Path] = []
    has_pl: bool | None = None
    page = sess.new_page()
    try:
        try:
            page.goto(order_url, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            page.goto(order_url, wait_until="commit", timeout=45000)
        page.wait_for_timeout(5000)
        sess.wait_if_login(page, order_url, log)

        # czekaj na zaladowanie strony zamowienia (SPA — dlugie ladowanie)
        try:
            page.get_by_text(amazon_order_number, exact=False).first.wait_for(timeout=30000)
        except Exception:
            log("  Amazon: strona zamowienia nie zaladowala sie — nie sprawdzono faktur.")
            return [], None
        page.wait_for_timeout(3000)

        # otworz modal 'Manage invoice' (z reload i druga proba)
        btn = _find_manage_invoice_button(page)
        if btn is None:
            log("  Amazon: brak przycisku 'Manage invoice' — przeladowuje strone...")
            try:
                page.reload(wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)
                page.get_by_text(amazon_order_number, exact=False).first.wait_for(timeout=20000)
            except Exception:
                pass
            btn = _find_manage_invoice_button(page)
        if btn is None:
            # screenshot diagnostyczny — zobaczymy co Amazon wyswietlil
            try:
                dbg = folder / f"{amazon_order_number}_DEBUG_brak_przycisku.png"
                page.screenshot(path=str(dbg), full_page=True)
                log(f"  Amazon: brak przycisku 'Manage invoice' (debug: {dbg.name})")
            except Exception:
                log("  Amazon: brak przycisku 'Manage invoice'.")
            return [], None

        try:
            btn.click(timeout=8000)
        except Exception:
            # JS click fallback
            try:
                page.evaluate("e => e.click()", btn)
            except Exception:
                log("  Amazon: nie udalo sie kliknac 'Manage invoice'.")
                return [], None

        try:
            page.get_by_text("Invoices for order", exact=False).first.wait_for(timeout=15000)
        except Exception:
            log("  Amazon: modal faktur nie otworzyl sie.")
            return [], None

        # wiersze modala laduja sie asynchronicznie — polluj do 16s
        pl_numbers: list[str] = []
        for _ in range(8):
            page.wait_for_timeout(2000)
            try:
                body_text = page.locator("body").inner_text(timeout=5000)
            except Exception:
                body_text = ""
            pl_numbers = list(dict.fromkeys(PL_INVOICE_RE.findall(body_text)))
            if pl_numbers:
                break
            # tabela juz jest (widac Download), ale bez PL -> mozna konczyc wczesniej
            if "Download" in body_text and _ >= 2:
                break
        if not pl_numbers:
            log("  Amazon: brak faktur PL w modalu (sprawdzono przez 16s).")
            return [], False
        has_pl = True

        for number in pl_numbers:
            try:
                btn = _find_download_button_near(page, number)
                if btn is None:
                    log(f"  Amazon: nie znaleziono przycisku Download dla {number}")
                    continue
                with page.expect_download(timeout=30000) as dl_info:
                    btn.click()
                download = dl_info.value
                out = folder / f"faktura_amazon_{number}.pdf"
                download.save_as(str(out))
                downloaded.append(out)
                log(f"  Amazon: pobrano fakture {number}")
            except Exception as exc:
                log(f"  Amazon: nie udalo sie pobrac {number}: {exc}")

        return downloaded, has_pl
    except Exception as exc:
        log(f"  Amazon faktury: blad: {exc}")
        return downloaded, has_pl
    finally:
        try:
            page.close()
        except Exception:
            pass
