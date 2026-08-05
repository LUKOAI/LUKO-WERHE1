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

# Numer zamowienia Amazon: XXX-XXXXXXX-XXXXXXX (3-7-7 cyfr).
# eBay/Allegro/inne platformy maja INNY format idExternal — po tym je odrozniamy.
AMAZON_ORDER_RE = re.compile(r"^\d{3}-\d{7}-\d{7}$")


def is_amazon_order_number(external_number: str) -> bool:
    """True gdy numer zewnetrzny ma format zamowienia Amazon (nie eBay/inne)."""
    return bool(AMAZON_ORDER_RE.match((external_number or "").strip()))


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


def _is_valid_pdf(path: Path) -> bool:
    """Sprawdza czy plik to prawdziwy PDF (naglowek %PDF + sensowny rozmiar)."""
    try:
        if path.stat().st_size < 8000:  # prawdziwa faktura ~60-80 KB; 6 KB = smiec
            return False
        with open(path, "rb") as fh:
            return fh.read(5).startswith(b"%PDF")
    except Exception:
        return False


def _download_url_for_number(page, number: str) -> str | None:
    """Wyciaga URL dokumentu (href) z linku Download przy danym numerze faktury.

    Amazon: przycisk Download to <a href="/documents/download/{uuid}/document.pdf">.
    Pobranie po URL z ciasteczkami sesji = gwarantowany prawdziwy PDF
    (bez problemow z klikaniem w niestabilnym modalu).
    """
    try:
        href = page.evaluate(
            """
            (num) => {
                // znajdz element z numerem faktury
                const all = Array.from(document.querySelectorAll('*'));
                let numEl = null;
                for (const el of all) {
                    if (el.children.length === 0 && (el.textContent || '').trim() === num) {
                        numEl = el; break;
                    }
                }
                if (!numEl) return null;
                // wiersz tabeli / kontener
                let row = numEl;
                for (let i = 0; i < 6 && row.parentElement; i++) {
                    row = row.parentElement;
                    const a = row.querySelector("a[href*='download'], a[href*='document'], a[download]");
                    if (a) return a.href;
                }
                // fallback: najblizszy link Download wzgledem pozycji
                const r0 = numEl.getBoundingClientRect();
                const links = Array.from(document.querySelectorAll("a[href*='download'], a[href*='document'], a[download]"));
                let best = null, bestD = 1e9;
                for (const a of links) {
                    const r = a.getBoundingClientRect();
                    const d = Math.abs((r.top + r.height/2) - (r0.top + r0.height/2));
                    if (d < bestD) { bestD = d; best = a; }
                }
                return best ? best.href : null;
            }
            """,
            number,
        )
        return href
    except Exception:
        return None


def _download_invoice_for_number(page, number: str, out_path: Path, log) -> bool:
    """Pobiera fakture PL o danym numerze do out_path. Zwraca True przy sukcesie.

    Kolejnosc (od najpewniejszej):
      1. URL dokumentu + fetch przez zalogowana sesje (page.context.request)
      2. Playwright klik na 'Download' + expect_download
      3. force-click
    Po kazdej probie waliduje, ze to prawdziwy PDF.
    """
    # Strategia 1: bezposredni fetch po URL (z ciasteczkami sesji)
    url = _download_url_for_number(page, number)
    if url:
        try:
            resp = page.context.request.get(url, timeout=30000)
            if resp.ok:
                body = resp.body()
                if body[:5].startswith(b"%PDF") and len(body) >= 8000:
                    out_path.write_bytes(body)
                    return True
        except Exception:
            pass

    # Strategie 2-3: klikanie przycisku Download (ten sam wiersz wizualny)
    try:
        num_el = page.get_by_text(number, exact=False).first
        num_el.wait_for(timeout=8000)
        num_el.scroll_into_view_if_needed(timeout=3000)
        page.wait_for_timeout(400)
        num_box = num_el.bounding_box()
        if not num_box:
            return False
        num_y = num_box["y"] + num_box["height"] / 2
        candidates = page.get_by_text("Download", exact=False)
        best, best_dist = None, 1e9
        for i in range(candidates.count()):
            el = candidates.nth(i)
            try:
                box = el.bounding_box()
            except Exception:
                continue
            if not box:
                continue
            y = box["y"] + box["height"] / 2
            if abs(y - num_y) < best_dist:
                best, best_dist = el, abs(y - num_y)
        if best is None:
            return False

        for clicker in (
            lambda: best.click(timeout=10000),
            lambda: best.click(force=True, timeout=10000),
        ):
            try:
                with page.expect_download(timeout=25000) as dl_info:
                    clicker()
                dl_info.value.save_as(str(out_path))
                if _is_valid_pdf(out_path):
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def _collect_pl_numbers_all_pages(page, log=None) -> list[str]:
    """Zbiera numery PL ze WSZYSTKICH stron modala (paginacja 1,2,3...).

    Amazon modal: na dole tabeli sa numery stron (< 1 2 3 >).
    Klikamy kazdy numer strony i zbieramy PL numery.
    """
    all_numbers: list[str] = []

    def _scan():
        try:
            text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            text = ""
        return list(dict.fromkeys(PL_INVOICE_RE.findall(text)))

    # polluj strone 1
    for _ in range(6):
        page.wait_for_timeout(2000)
        nums = _scan()
        all_numbers.extend(nums)
        if nums:
            break
        try:
            body = page.locator("body").inner_text(timeout=3000)
            if "Download" in body and _ >= 2:
                break
        except Exception:
            pass

    # Sprawdz czy sa dodatkowe strony — szukamy numerow stron w modalu
    # Modal ma paginacje: < 1 2 3 >  — klikamy 2, 3, itd.
    for page_num in range(2, 10):
        try:
            # Szukamy klikalnego elementu z numerem strony w kontekscie modala
            # (nie moze byc zbyt ogolny zeby nie kliknac czegos innego)
            page_btn = page.evaluate_handle(f"""
                () => {{
                    const modal = document.querySelector('[role="dialog"], [class*="modal"], [class*="Modal"]');
                    const root = modal || document;
                    const candidates = root.querySelectorAll('button, a, span[role="button"], [tabindex]');
                    for (const el of candidates) {{
                        const txt = (el.textContent || '').trim();
                        if (txt === '{page_num}') return el;
                    }}
                    return null;
                }}
            """)
            if not page_btn or str(page_btn) == "JSHandle@null":
                break
            el = page_btn.as_element()
            if el is None:
                break
            page.evaluate("e => e.click()", el)
            page.wait_for_timeout(3000)
            nums = _scan()
            new = [n for n in nums if n not in all_numbers]
            all_numbers.extend(new)
            if log and new:
                log(f"  Amazon: strona {page_num} modala: +{len(new)} faktur PL")
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
        pl_numbers = _collect_pl_numbers_all_pages(page, log=log)
        if not pl_numbers:
            log("  Amazon: brak faktur PL w modalu (wszystkie strony sprawdzone).")
            return [], False
        has_pl = True
        log(f"  Amazon: znaleziono {len(pl_numbers)} faktur PL: {', '.join(pl_numbers[:5])}")

        # Wracamy na strone 1 modala (klikamy numer '1')
        try:
            page1_btn = page.evaluate_handle("""
                () => {
                    const modal = document.querySelector('[role="dialog"], [class*="modal"], [class*="Modal"]');
                    const root = modal || document;
                    const els = root.querySelectorAll('button, a, span[role="button"], [tabindex]');
                    for (const el of els) {
                        if ((el.textContent || '').trim() === '1') return el;
                    }
                    return null;
                }
            """)
            if page1_btn and str(page1_btn) != "JSHandle@null":
                page.evaluate("e => e.click()", page1_btn.as_element())
                page.wait_for_timeout(2000)
        except Exception:
            pass

        # Pobierz kazda fakture PL — przechodzac przez strony modala
        remaining = set(pl_numbers)
        max_pages = 5
        for page_num in range(max_pages):
            for number in list(remaining):
                try:
                    page.get_by_text(number, exact=False).first.wait_for(timeout=2000)
                except Exception:
                    continue
                out = folder / f"faktura_amazon_{number}.pdf"
                if _download_invoice_for_number(page, number, out, log):
                    downloaded.append(out)
                    remaining.discard(number)
                    size_kb = out.stat().st_size // 1024
                    log(f"  Amazon: pobrano fakture {number} ({size_kb} KB)")
                    page.wait_for_timeout(800)
                else:
                    log(f"  Amazon: nie udalo sie pobrac {number} (niepoprawny PDF)")
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
