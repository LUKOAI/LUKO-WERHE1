from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


DEFAULT_CONFIG_PATH = Path("config.json")


@dataclass
class AppConfig:
    apilo_base_url: str = "https://api.apilo.com"
    apilo_orders_endpoint: str = "/orders"
    apilo_order_details_endpoint: str = "/orders/{order_id}"
    apilo_token: str = ""
    output_root: str = "output"
    playwright_headless: bool = True
    tracking_timeout_ms: int = 45000
    screenshot_full_page_fallback: bool = True
    pdf_company_name: str = "WERHE / WERKON Polska"


class ConfigError(Exception):
    pass


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    load_dotenv()
    if not path.exists():
        raise ConfigError(
            f"Brak pliku konfiguracyjnego: {path}. Uruchom aplikację i zapisz token."
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    config = AppConfig(**data)

    if not config.apilo_token:
        raise ConfigError("Pole 'apilo_token' jest puste w config.json.")

    return config


def save_config(config: AppConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def bootstrap_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Tworzy domyślną konfigurację jeśli nie istnieje."""
    if path.exists():
        return load_config(path)
    cfg = AppConfig()
    save_config(cfg, path)
    return cfg


def safe_config_preview(config: AppConfig) -> str:
    masked = config.apilo_token[:4] + "..." if config.apilo_token else "<brak>"
    return (
        f"API: {config.apilo_base_url} | endpoint: {config.apilo_orders_endpoint} | "
        f"token: {masked}"
    )
