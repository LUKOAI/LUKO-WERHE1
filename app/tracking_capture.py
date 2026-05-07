from __future__ import annotations

from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.config import AppConfig


DELIVERED_KEYWORDS = [
    "doręcz", "delivered", "delivered at", "delivered on", "shipment delivered", "proof of delivery"
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
        browser = p.chromium.launch(headless=config.playwright_headless)
        context = browser.new_context(viewport={"width": 1600, "height": 2000})
        page = context.new_page()

        try:
            page.goto(tracking_url, wait_until="domcontentloaded", timeout=config.tracking_timeout_ms)
            page.wait_for_timeout(1500)

            found = False
            for keyword in DELIVERED_KEYWORDS:
                locator = page.get_by_text(keyword, exact=False)
                try:
                    locator.first.wait_for(timeout=2500)
                    box = locator.first.bounding_box()
                    if box:
                        clip = {
                            "x": max(box["x"] - 20, 0),
                            "y": max(box["y"] - 140, 0),
                            "width": min(box["width"] + 500, 1500),
                            "height": min(box["height"] + 500, 1100),
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
                        f"Nie znaleziono potwierdzenia doręczenia dla {carrier}: {tracking_url}"
                    )

            return output_path
        finally:
            context.close()
            browser.close()
