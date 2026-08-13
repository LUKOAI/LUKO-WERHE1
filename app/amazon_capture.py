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
        # Decyduje magic %PDF — smieci (HTML logowania itp.) go nie maja.
        # Prog rozmiaru niski (1 KB): proste faktury/kredytowki bywaja male.
        if path.stat().st_size < 1000:
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


def _form_request_for_number(page, number: str):
    """Odczytuje FORMULARZ przycisku Download przy numerze (nowy UI: input submit w <form>).

    Zwraca {action, method, fields:{...}} albo None. Wyslanie tego formularza
    przez zalogowana sesje = pobranie bez klikania (odporne na degradacje modala).
    """
    try:
        return page.evaluate(
            """
            (num) => {
                const all = Array.from(document.querySelectorAll('*'));
                let numEl = null;
                for (const el of all) {
                    if (el.children.length === 0 && (el.textContent || '').trim() === num) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) { numEl = el; break; }
                    }
                }
                if (!numEl) return null;
                const serialize = (form) => {
                    const fields = {};
                    for (const inp of form.querySelectorAll('input[name], select[name], textarea[name]')) {
                        if (inp.type === 'submit' || inp.type === 'button') continue;
                        fields[inp.name] = inp.value || '';
                    }
                    return { action: form.action || '', method: (form.method || 'get').toUpperCase(), fields };
                };
                // 1) form w wierszu (wspolny przodek z numerem)
                let row = numEl;
                for (let i = 0; i < 7 && row.parentElement; i++) {
                    row = row.parentElement;
                    for (const form of row.querySelectorAll('form')) {
                        if (form.querySelector("input[type='submit']") && form.action)
                            return serialize(form);
                    }
                }
                // 2) form najblizszy pozycyjnie (ten sam wiersz wizualny)
                const r0 = numEl.getBoundingClientRect();
                let best = null, bestD = 1e9;
                for (const form of document.querySelectorAll('form')) {
                    if (!form.action || !form.querySelector("input[type='submit']")) continue;
                    const r = form.getBoundingClientRect();
                    if (r.width === 0) continue;
                    const d = Math.abs((r.top + r.height/2) - (r0.top + r0.height/2));
                    if (d < bestD) { bestD = d; best = form; }
                }
                return (best && bestD <= 80) ? serialize(best) : null;
            }
            """,
            number,
        )
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
    # Strategia 1: bezposredni fetch po URL (z ciasteczkami sesji + Referer)
    url = _download_url_for_number(page, number)
    if url:
        try:
            resp = page.context.request.get(
                url, timeout=30000,
                headers={
                    "Referer": page.url,
                    "Accept": "application/pdf,application/octet-stream,*/*",
                },
            )
            body = resp.body() if resp.ok else b""
            if body[:5].startswith(b"%PDF") and len(body) >= 1000:
                out_path.write_bytes(body)
                return True
            log(f"    [diag {number}] fetch URL: status={resp.status}, "
                f"typ={resp.headers.get('content-type','?')}, {len(body)}B, "
                f"start={body[:12]!r}")
        except Exception as exc:
            log(f"    [diag {number}] fetch URL blad: {exc}")

    # Strategia 1b: FORMULARZ przycisku Download (nowy UI) — submit przez sesje,
    # zero klikania, odporne na degradacje modala po dlugiej sesji
    form = _form_request_for_number(page, number)
    if form and form.get("action"):
        try:
            headers = {
                "Referer": page.url,
                "Accept": "application/pdf,application/octet-stream,*/*",
            }
            if form.get("method") == "POST":
                resp = page.context.request.post(
                    form["action"], form=form.get("fields") or {},
                    timeout=30000, headers=headers)
            else:
                resp = page.context.request.get(
                    form["action"], params=form.get("fields") or {},
                    timeout=30000, headers=headers)
            body = resp.body() if resp.ok else b""
            if body[:5].startswith(b"%PDF") and len(body) >= 1000:
                out_path.write_bytes(body)
                return True
            log(f"    [diag {number}] form {form.get('method')}: status={resp.status}, "
                f"typ={resp.headers.get('content-type','?')}, {len(body)}B")
        except Exception as exc:
            log(f"    [diag {number}] form submit blad: {str(exc)[:120]}")
    else:
        log(f"    [diag {number}] brak <a href> i <form> przy numerze — probuje klik")

    # Strategie 2-3: klikanie przycisku Download (ten sam wiersz wizualny)
    try:
        # numer moze wystepowac w DOM wielokrotnie (takze niewidocznie) —
        # bierzemy pierwsze WIDOCZNE wystapienie, scroll nie moze blokowac
        matches = page.get_by_text(number, exact=False)
        matches.first.wait_for(timeout=8000)
        num_el = None
        for i in range(min(matches.count(), 10)):
            cand = matches.nth(i)
            try:
                if cand.is_visible():
                    num_el = cand
                    break
            except Exception:
                continue
        if num_el is None:
            log(f"    [diag {number}] brak WIDOCZNEGO wystapienia numeru")
            return False
        try:
            num_el.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass  # scroll bywa flaky — nie przerywamy
        page.wait_for_timeout(400)
        num_box = num_el.bounding_box()
        if not num_box:
            log(f"    [diag {number}] numer niewidoczny (bounding_box=None)")
            return False
        num_y = num_box["y"] + num_box["height"] / 2

        # kandydaci: tekst 'Download' ORAZ input[value='Download'] (nowy UI a-button)
        best, best_dist = None, 1e9
        for loc in (
            page.get_by_text("Download", exact=False),
            page.locator("input[type='submit'][value='Download']"),
        ):
            try:
                n = loc.count()
            except Exception:
                continue
            for i in range(n):
                el = loc.nth(i)
                try:
                    if not el.is_visible():
                        continue
                    box = el.bounding_box()
                except Exception:
                    continue
                if not box:
                    continue
                y = box["y"] + box["height"] / 2
                if abs(y - num_y) < best_dist:
                    best, best_dist = el, abs(y - num_y)
        if best is None:
            log(f"    [diag {number}] brak przycisku Download na stronie")
            return False

        def _js_click_nearest():
            """JS: klika input/button/a Download najblizszy numerowi (omija overlay)."""
            page.evaluate(
                """
                (num) => {
                    const all = Array.from(document.querySelectorAll('*'));
                    let numEl = null;
                    for (const el of all) {
                        if (el.children.length === 0 && (el.textContent || '').trim() === num) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) { numEl = el; break; }
                        }
                    }
                    if (!numEl) throw new Error('brak numeru');
                    const r0 = numEl.getBoundingClientRect();
                    const cands = [];
                    for (const inp of document.querySelectorAll("input[type='submit']"))
                        if (/download/i.test(inp.value || '')) cands.push(inp);
                    for (const b of document.querySelectorAll('button, a'))
                        if (/^download$/i.test((b.textContent || '').trim())) cands.push(b);
                    // nowy UI: tekst w spanie, klikalny input obok (value bywa puste)
                    for (const sp of document.querySelectorAll('span')) {
                        if (!/^download$/i.test((sp.textContent || '').trim())) continue;
                        const btn = sp.closest('.a-button, [class*="button" i]') || sp.parentElement;
                        const inp = btn ? btn.querySelector('input') : null;
                        cands.push(inp || sp);
                    }
                    let best = null, bestD = 1e9;
                    for (const c of cands) {
                        const r = c.getBoundingClientRect();
                        if (r.width === 0) continue;
                        const d = Math.abs((r.top + r.height/2) - (r0.top + r0.height/2));
                        if (d < bestD) { bestD = d; best = c; }
                    }
                    if (!best) throw new Error('brak przycisku');
                    best.click();
                }
                """,
                number,
            )

        for name, clicker in (
            ("klik", lambda: best.click(timeout=10000)),
            ("force-klik", lambda: best.click(force=True, timeout=10000)),
            ("js-klik", _js_click_nearest),
        ):
            try:
                with page.expect_download(timeout=25000) as dl_info:
                    clicker()
                dl_info.value.save_as(str(out_path))
                if _is_valid_pdf(out_path):
                    return True
                # zachowaj zly plik do diagnozy
                size = out_path.stat().st_size if out_path.exists() else 0
                head = open(out_path, "rb").read(12) if out_path.exists() else b""
                bad = out_path.with_name(f"{out_path.stem}_INVALID.bin")
                try:
                    out_path.replace(bad)
                except Exception:
                    pass
                log(f"    [diag {number}] {name}: pobrano {size}B, start={head!r} "
                    f"(zachowano {bad.name})")
            except Exception as exc:
                log(f"    [diag {number}] {name} nieudany: {str(exc)[:120]}")
                continue
    except Exception as exc:
        log(f"    [diag {number}] blad klikania: {str(exc)[:120]}")
        return False
    return False


def _collect_pl_numbers_all_pages(page, log=None) -> list[str]:
    """Zbiera numery PL ze WSZYSTKICH stron modala (paginacja 1,2,3...).

    Amazon modal: na dole tabeli sa numery stron (< 1 2 3 >).
    Klikamy kazdy numer strony i zbieramy PL numery.
    """
    all_numbers: list[str] = []

    def _all_frames_text() -> str:
        """Tekst z glownego dokumentu + wszystkich iframe (modal moze byc w ramce)."""
        parts = []
        for fr in page.frames:
            try:
                parts.append(fr.locator("body").inner_text(timeout=2500))
            except Exception:
                continue
        return "\n".join(parts)

    def _scan():
        return list(dict.fromkeys(PL_INVOICE_RE.findall(_all_frames_text())))

    # polluj strone 1
    saw_download = False
    for _ in range(6):
        page.wait_for_timeout(2000)
        text = _all_frames_text()
        nums = list(dict.fromkeys(PL_INVOICE_RE.findall(text)))
        all_numbers.extend(nums)
        if "Download" in text:
            saw_download = True
        if nums:
            break
        if saw_download and _ >= 2:
            break
    if log and not saw_download and not all_numbers:
        log("  Amazon: UWAGA — w modalu nie widac ani faktur, ani przycisku Download"
            " (mozliwy problem renderowania)")

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
    """Szuka przycisku 'Manage invoice' — stary i NOWY Seller Central.

    Nowy UI (potwierdzony HTML od klienta):
      <span data-test-id="manage-idu-invoice-button" class="a-button">
        <input class="a-button-input" type="submit" value="Manage invoice">
        <span class="a-button-text" aria-hidden="true">Manage invoice</span>
    Klikalny jest INPUT (submit) — tekst w spanie jest tylko dekoracja,
    JS-klik na spanie nic nie robi. Dlatego zawsze celujemy w input.
    """
    strategies = [
        # NOWY UI: stabilny data-test-id — najpierw wewnetrzny input, potem kontener
        lambda: page.locator("[data-test-id='manage-idu-invoice-button'] input").first,
        lambda: page.locator("[data-test-id='manage-idu-invoice-button']").first,
        # input[type=submit] z value 'Manage invoice' (bez data-test-id)
        lambda: page.locator("input[type='submit'][value='Manage invoice']").first,
        # STARY UI: klasyczne locatory
        lambda: page.get_by_role("button", name=re.compile(r"manage invoices?", re.I)).first,
        lambda: page.get_by_text(re.compile(r"Manage invoices?", re.I)).first,
    ]
    for make in strategies:
        try:
            el = make()
            el.wait_for(timeout=4000)
            el.scroll_into_view_if_needed(timeout=3000)
            return el
        except Exception:
            continue

    # JS fallback: uwzglednia inputy (value) i zwraca element KLIKALNY
    try:
        handle = page.evaluate_handle("""
            () => {
                const byId = document.querySelector(
                    "[data-test-id='manage-idu-invoice-button'] input, [data-test-id='manage-idu-invoice-button']");
                if (byId) return byId;
                for (const inp of document.querySelectorAll("input[type='submit']")) {
                    if (/manage invoices?/i.test(inp.value || '')) return inp;
                }
                const all = document.querySelectorAll('span, button, a, div');
                for (const el of all) {
                    const txt = (el.textContent || '').trim();
                    if (/^manage invoices?$/i.test(txt)) {
                        const inp = el.querySelector('input');  // klikaj input, nie span
                        return inp || el;
                    }
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
            # screenshot diagnostyczny modala — odroznimy prawdziwy brak PL
            # od problemu z renderowaniem/iframe
            try:
                dbg = folder / f"{amazon_order_number}_DEBUG_modal.png"
                page.screenshot(path=str(dbg))
                log(f"  Amazon: brak faktur PL w modalu (debug: {dbg.name})")
            except Exception:
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
