from __future__ import annotations

from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.config import AppConfig


DELIVERED_KEYWORDS = [
    "delivered", "delivered at", "delivered on", "shipment delivered",
    "proof of delivery", "zugestellt", "doręcz", "dostarczona",
]

# Kurierzy z dedykowanym przycinaniem miedzy stalymi kotwicami tekstowymi.
# Poczta Polska (emonitoring): od "Dane przesyłki" do przycisku
# "Instrukcja pobrania poświadczonego zgłoszenia celnego" (stale elementy strony).
CARRIER_CROP_ANCHORS = {
    "poczta-polska": {
        "top": "Dane przesyłki",
        "bottom": "Instrukcja pobrania poświadczonego zgłoszenia celnego",
        "bottom_fallback": "Doręczona",
    },
}


class TrackingCaptureError(Exception):
    pass


def _anchors_for(tracking_url: str, carrier: str) -> dict | None:
    u = (tracking_url or "").lower()
    c = (carrier or "").upper()
    if "poczta-polska" in u or "POCZT" in c:
        return CARRIER_CROP_ANCHORS["poczta-polska"]
    return None


def _abs_rect(page, text: str):
    try:
        el = page.get_by_text(text, exact=False).first
        el.wait_for(timeout=4000)
        return el.evaluate(
            "e=>{const r=e.getBoundingClientRect();"
            "return {top:r.top+window.scrollY,bottom:r.bottom+window.scrollY};}"
        )
    except Exception:
        return None


def _crop_between(page, output_path: Path, anchors: dict) -> bool:
    """Full-page screenshot przyciety od kotwicy gornej do dolnej (Pillow)."""
    tmp = output_path.with_name(output_path.stem + "_full.png")
    page.screenshot(path=str(tmp), full_page=True)
    try:
        from PIL import Image
        img = Image.open(tmp)
        W, H = img.size
        top, bottom = 0, H
        tr = _abs_rect(page, anchors["top"])
        if tr:
            top = max(0, int(tr["top"]) - 60)
        br = _abs_rect(page, anchors["bottom"])
        if not br and anchors.get("bottom_fallback"):
            br = _abs_rect(page, anchors["bottom_fallback"])
        if br:
            bottom = min(H, int(br["bottom"]) + 30)
        if bottom <= top:
            top, bottom = 0, H
        img.crop((0, top, W, bottom)).save(output_path)
        try:
            tmp.unlink()
        except Exception:
            pass
        return True
    except Exception:
        try:
            tmp.replace(output_path)
        except Exception:
            pass
        return output_path.exists()


def capture_tracking_screenshot(
    tracking_url: str,
    output_path: Path,
    config: AppConfig,
    carrier: str = "",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # Firefox jest mniej blokowany niz Chromium (np. UPS)
        browser = p.firefox.launch(headless=config.playwright_headless)
        context = browser.new_context(
            viewport={"width": 1400, "height": 1800},
            locale="en-US",
        )
        page = context.new_page()

        try:
            try:
                page.goto(tracking_url, wait_until="domcontentloaded",
                          timeout=config.tracking_timeout_ms)
            except Exception:
                page.goto(tracking_url, wait_until="commit",
                          timeout=config.tracking_timeout_ms)

            page.wait_for_timeout(4000)
            _dismiss_cookies(page)
            page.wait_for_timeout(3000)

            # Kurier ze stalymi kotwicami (np. Poczta Polska) — przytnij dokladny zakres
            anchors = _anchors_for(tracking_url, carrier)
            if anchors:
                if _crop_between(page, output_path, anchors):
                    return output_path

            found = False
            for keyword in DELIVERED_KEYWORDS:
                locator = page.get_by_text(keyword, exact=False)
                try:
                    locator.first.wait_for(timeout=3000)
                    box = locator.first.bounding_box()
                    if box:
                        clip = {
                            "x": 0,
                            "y": max(box["y"] - 180, 0),
                            "width": 1400,
                            "height": min(box["height"] + 700, 1400),
                        }
                        page.screenshot(path=str(output_path), clip=clip)
                        found = True
                        break
                except PlaywrightTimeoutError:
                    continue

            if not found:
                if config.screenshot_full_page_fallback:
                    page.screenshot(path=str(output_path), full_page=True)
                else:
                    raise TrackingCaptureError(
                        f"Nie znaleziono potwierdzenia doreczenia: {tracking_url}"
                    )

            return output_path
        finally:
            context.close()
            browser.close()


def _dismiss_cookies(page) -> None:
    selectors = [
        "#onetrust-accept-btn-handler",
        "button[id*='accept']",
        "button[class*='accept']",
        "button:has-text('Accept')",
        "button:has-text('Accept All')",
        "button:has-text('Agree')",
        "button:has-text('Akceptuj')",
        "button:has-text('I Agree')",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1000):
                btn.click()
                page.wait_for_timeout(500)
                return
        except Exception:
            continue
