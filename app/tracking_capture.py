from __future__ import annotations

from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.config import AppConfig


DELIVERED_KEYWORDS = [
    "delivered", "delivered at", "delivered on", "shipment delivered",
    "proof of delivery", "zugestellt", "doręcz", "dostarczona",
]


class TrackingCaptureError(Exception):
    pass


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

            found = False
            for keyword in DELIVERED_KEYWORDS:
                locator = page.get_by_text(keyword, exact=False)
                try:
                    locator.first.wait_for(timeout=3000)
                    box = locator.first.bounding_box()
                    if box:
                        clip = {
                            "x": max(box["x"] - 20, 0),
                            "y": max(box["y"] - 160, 0),
                            "width": min(box["width"] + 600, 1400),
                            "height": min(box["height"] + 600, 1200),
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
