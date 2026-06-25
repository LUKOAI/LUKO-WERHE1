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


def _click_download_for_number(page, number: str, log) -> Path | None:
    """Klika Download przy numerze faktury i pobiera plik.

    Uzywa JS click (pomija problemy z 'waiting for element to be stable')
    oraz szuka przycisku po pozycji (ten sam wiersz wizualny).
    """
    try:
        num_el = page.get_by_text(number, exact=False).first
        num_el.wait_for(timeout=8000)
        num_el.scroll_into_view_if_needed(timeout=3000)
        page.wait_for_timeout(500)
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
        if best is None:
            return None

        # JS click — stabilniejszy niz Playwright click (modal cesto blokuje)
        try:
            with page.expect_download(timeout=30000) as dl_info:
                page.evaluate("e => e.click()", best)
            return dl_info.value
        except Exception:
            # fallback: Playwright force-click
            try:
                with page.expect_download(timeout=20000) as dl_info:
                    best.click(force=True, timeout=10000)
                return dl_info.value
            except Exception:
                return None
    except Exception:
        return None


def _collect_pl_numbers_all_pages(page) -> list[str]:
    """Zbiera numery PL ze WSZYSTKICH stron modala (paginacja 1,2,3...)."""
    all_numbers: list[str] = []

    def _scan_current_page():
        try:
            text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            text = ""
        return list(dict.fromkeys(PL_INVOICE_RE.findall(text)))

    # polluj strone 1
    for _ in range(6):
        page.wait_for_timeout(2000)
        nums = _scan_current_page()
        if nums or "Download" in (page.locator("body").inner_text(timeout=3000) if True else ""):
            all_numbers.extend(nums)
            break

    # przejdz przez kolejne strony modala (jesli sa)
    while True:
        try:
            # szukamy przycisku nastepnej strony (> lub numer strony)
            next_btn = page.locator("button:has-text('>'), a:has-text('>')").first
            if not next_btn.is_visible(timeout=2000):
                break
            next_btn.click(timeout=5000)
            page.wait_for_timeout(2500)
            nums = _scan_current_page()
            new = [n for n in nums if n not in all_numbers]
            all_numbers.extend(new)
            if not new:
                break
        except Exception:
            break

    return list(dict.fromkeys(all_numbers))


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

        # Zbierz numery PL ze WSZYSTKICH stron modala (paginacja 1,2,3...)
        pl_numbers = _collect_pl_numbers_all_pages(page)
        if not pl_numbers:
            log("  Amazon: brak faktur PL w modalu (wszystkie strony sprawdzone).")
            return [], False
        has_pl = True
        log(f"  Amazon: znaleziono {len(pl_numbers)} faktur PL: {', '.join(pl_numbers[:5])}")

        # Wracamy na strone 1 modala (klikamy '<' wielokrotnie lub 1)
        for _ in range(5):
            try:
                prev = page.locator("button:has-text('<'), a:has-text('<')").first
                if prev.is_visible(timeout=1000):
                    prev.click(timeout=3000)
                    page.wait_for_timeout(1000)
                else:
                    break
            except Exception:
                break

        # Pobierz kazda fakture PL — przechodzac przez strony modala
        remaining = set(pl_numbers)
        max_pages = 5
        for page_num in range(max_pages):
            for number in list(remaining):
                try:
                    page.get_by_text(number, exact=False).first.wait_for(timeout=2000)
                except Exception:
                    continue
                dl = _click_download_for_number(page, number, log)
                if dl:
                    out = folder / f"faktura_amazon_{number}.pdf"
                    dl.save_as(str(out))
                    downloaded.append(out)
                    remaining.discard(number)
                    log(f"  Amazon: pobrano fakture {number}")
                    page.wait_for_timeout(1000)
                else:
                    log(f"  Amazon: nie udalo sie pobrac {number}")
                    remaining.discard(number)
            if not remaining:
                break
            # nastepna strona modala
            try:
                nxt = page.locator("button:has-text('>'), a:has-text('>')").first
                if nxt.is_visible(timeout=2000):
                    nxt.click(timeout=5000)
                    page.wait_for_timeout(2500)
                else:
                    break
            except Exception:
                break

        return downloaded, has_pl
    except Exception as exc:
        log(f"  Amazon faktury: blad: {exc}")
        return downloaded, has_pl
    finally:
        try:
            page.close()
        except Exception:
            pass
