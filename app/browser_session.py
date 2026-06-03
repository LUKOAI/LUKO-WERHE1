from __future__ import annotations

from pathlib import Path
from typing import Callable

from playwright.sync_api import sync_playwright

from app.config import AppConfig


# Adresy stron logowania dla każdego serwisu
LOGIN_URLS = {
    "amazon": "https://{domain}/",
    "apilo": "{panel_url}/",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class BrowserSessionError(Exception):
    pass


def _profile_dir(config: AppConfig, site: str) -> Path:
    """Katalog trwałego profilu przegladarki dla danego serwisu."""
    base = Path(config.browser_profiles_dir)
    path = base / site
    path.mkdir(parents=True, exist_ok=True)
    return path


def _login_url(config: AppConfig, site: str) -> str:
    if site == "amazon":
        return LOGIN_URLS["amazon"].format(domain=config.amazon_seller_domain)
    if site == "apilo":
        if not config.apilo_panel_url:
            raise BrowserSessionError(
                "Brak adresu panelu Apilo (apilo_panel_url) w konfiguracji."
            )
        return LOGIN_URLS["apilo"].format(panel_url=config.apilo_panel_url.rstrip("/"))
    raise BrowserSessionError(f"Nieznany serwis: {site}")


def open_login(site: str, config: AppConfig, on_done: Callable[[], None] | None = None,
               log_cb: Callable[[str], None] | None = None) -> None:
    """Otwiera WIDOCZNA przegladarke na stronie logowania danego serwisu.

    Klient loguje sie recznie (z 2FA). Sesja zapisuje sie w trwalym profilu.
    Przegladarka pozostaje otwarta dopoki uzytkownik jej nie zamknie —
    po zamkniciu sesja (cookies) jest juz zapisana w profilu na dysku.
    """
    def log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    profile = _profile_dir(config, site)
    url = _login_url(config, site)

    log(f"Otwieram przegladarke do logowania ({site}). Zaloguj sie recznie.")
    log("Po zalogowaniu ZAMKNIJ okno przegladarki — sesja zostanie zapisana.")

    with sync_playwright() as p:
        context = p.firefox.launch_persistent_context(
            user_data_dir=str(profile),
            headless=False,
            viewport={"width": 1500, "height": 950},
            user_agent=USER_AGENT,
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            log(f"Nie udalo sie otworzyc {url}: {exc}")

        # Czekamy az uzytkownik zamknie przegladarke (zalogowawszy sie)
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
        try:
            context.close()
        except Exception:
            pass

    log(f"Sesja {site} zapisana w profilu: {profile}")
    if on_done:
        on_done()


def has_session(config: AppConfig, site: str) -> bool:
    """Sprawdza czy istnieje zapisany profil dla serwisu (czy logowano sie wczesniej)."""
    profile = Path(config.browser_profiles_dir) / site
    # Firefox profil zawiera m.in. cookies.sqlite po zalogowaniu
    return profile.exists() and any(profile.iterdir())


class CaptureSession:
    """Otwiera trwaly profil przegladarki do robienia wielu screenshotow.

    Uzycie:
        with CaptureSession("amazon", config) as sess:
            sess.capture(url, output_path)
    """

    def __init__(self, site: str, config: AppConfig, headless: bool = False) -> None:
        self.site = site
        self.config = config
        self.headless = headless
        self._pw = None
        self._context = None

    def __enter__(self) -> "CaptureSession":
        profile = _profile_dir(self.config, self.site)
        self._pw = sync_playwright().start()
        self._context = self._pw.firefox.launch_persistent_context(
            user_data_dir=str(profile),
            headless=self.headless,
            viewport={"width": 1500, "height": 1100},
            user_agent=USER_AGENT,
        )
        return self

    def capture(self, url: str, output_path: Path, wait_ms: int = 5000,
                clip_keyword: str | None = None,
                log_cb: Callable[[str], None] | None = None) -> Path | None:
        """Otwiera URL i robi screenshot. Zwraca sciezke lub None przy bledzie.

        Jesli Amazon/Apilo wyswietli ekran logowania lub kod 2FA (takze w trakcie
        pracy), wykrywa to i CZEKA az uzytkownik wpisze dane w widocznym oknie.
        """
        def log(m: str) -> None:
            if log_cb:
                log_cb(m)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        page = self._context.new_page()
        try:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                page.goto(url, wait_until="commit", timeout=45000)
            page.wait_for_timeout(wait_ms)

            # Wykrycie ekranu logowania / 2FA (kod autoryzacji)
            self._wait_if_login(page, url, log)

            if clip_keyword:
                try:
                    loc = page.get_by_text(clip_keyword, exact=False).first
                    loc.wait_for(timeout=4000)
                    box = loc.bounding_box()
                    if box:
                        clip = {
                            "x": 0,
                            "y": max(box["y"] - 200, 0),
                            "width": 1500,
                            "height": min(box["height"] + 800, 1400),
                        }
                        page.screenshot(path=str(output_path), clip=clip)
                        return output_path
                except Exception:
                    pass

            page.screenshot(path=str(output_path), full_page=True)
            return output_path
        except Exception:
            return None
        finally:
            try:
                page.close()
            except Exception:
                pass

    # Markery URL-a wskazujace na ekran logowania / kodu 2FA Amazon
    _LOGIN_MARKERS = ("signin", "/ap/", "mfa", "two-step", "transition", "/login", "cvf")

    def _wait_if_login(self, page, target_url: str,
                       log: Callable[[str], None]) -> None:
        """Jesli strona to logowanie/2FA — czeka az uzytkownik je przejdzie (do 5 min)."""
        def looks_like_login() -> bool:
            try:
                u = (page.url or "").lower()
            except Exception:
                return False
            return any(m in u for m in self._LOGIN_MARKERS)

        if not looks_like_login():
            return

        log("UWAGA: serwis prosi o logowanie/kod 2FA. Wpisz dane w OTWARTYM oknie przegladarki...")
        # Czekamy do 5 minut (150 x 2s) az uzytkownik przejdzie logowanie
        for _ in range(150):
            page.wait_for_timeout(2000)
            if not looks_like_login():
                log("Logowanie zakonczone — kontynuuje.")
                # Wroc na strone zamowienia jesli nas przekierowalo
                try:
                    if target_url.split("?")[0] not in (page.url or ""):
                        page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(3000)
                except Exception:
                    pass
                return
        log("Limit czasu logowania (5 min) — pomijam to zamowienie.")

    def __exit__(self, *exc) -> None:
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
