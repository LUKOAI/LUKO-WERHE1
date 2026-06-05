from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_CONFIG_PATH = Path("config.json")


@dataclass
class AppConfig:
    apilo_base_url: str = "https://api.apilo.com"
    apilo_client_id: str = ""
    apilo_client_secret: str = ""
    apilo_auth_code: str = ""
    apilo_access_token: str = ""
    apilo_refresh_token: str = ""
    apilo_token_expires_at: str = ""
    output_root: str = "output"
    playwright_headless: bool = True
    tracking_timeout_ms: int = 45000
    screenshot_full_page_fallback: bool = True
    pdf_company_name: str = "WERHE / WERKON Polska"
    # Amazon Seller Central + panel Apilo (screenshoty)
    amazon_seller_domain: str = "sellercentral-europe.amazon.com"
    amazon_seller_domain_na: str = "sellercentral.amazon.com"
    apilo_panel_url: str = ""
    browser_profiles_dir: str = "browser_profiles"
    capture_amazon: bool = True
    capture_apilo_panel: bool = True
    download_pl_invoices: bool = True


class ConfigError(Exception):
    pass


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    load_dotenv()
    if not path.exists():
        raise ConfigError(
            f"Brak pliku konfiguracyjnego: {path}. Uruchom aplikację i zapisz dane."
        )

    data = json.loads(path.read_text(encoding="utf-8"))

    # Migracja ze starego formatu
    if "apilo_token" in data and "apilo_auth_code" not in data:
        data["apilo_auth_code"] = data.pop("apilo_token")
    for old_key in ("apilo_token", "apilo_orders_endpoint", "apilo_order_details_endpoint"):
        data.pop(old_key, None)

    known_fields = {f for f in AppConfig.__dataclass_fields__}
    filtered_data = {k: v for k, v in data.items() if k in known_fields}
    return AppConfig(**filtered_data)


def save_config(config: AppConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def bootstrap_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    if path.exists():
        return load_config(path)
    cfg = AppConfig()
    save_config(cfg, path)
    return cfg


def safe_config_preview(config: AppConfig) -> str:
    cid = config.apilo_client_id[:6] + "..." if config.apilo_client_id else "<brak>"
    has_token = "tak" if config.apilo_access_token else "nie"
    expires = config.apilo_token_expires_at or "n/a"
    return (
        f"API: {config.apilo_base_url} | client_id: {cid} | "
        f"access_token: {has_token} | wygasa: {expires}"
    )
