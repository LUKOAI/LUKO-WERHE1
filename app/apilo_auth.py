from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from app.config import AppConfig, save_config, DEFAULT_CONFIG_PATH

logger = logging.getLogger("werhe_tool")

TOKEN_ENDPOINT = "/rest/auth/token/"
# Apilo access_token ważny 21 dni — odświeżamy z marginesem 1 dnia
TOKEN_SAFETY_MARGIN = timedelta(days=1)


class ApiloAuthError(Exception):
    pass


def _post_token(base_url: str, client_id: str, client_secret: str,
                body: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    url = base_url.rstrip("/") + TOKEN_ENDPOINT
    try:
        resp = requests.post(
            url,
            json=body,
            auth=(client_id, client_secret),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise ApiloAuthError(f"Błąd autentykacji Apilo: {exc}") from exc


def authenticate(config: AppConfig) -> AppConfig:
    """Wymiana kodu autoryzacji na access_token + refresh_token."""
    if not config.apilo_client_id or not config.apilo_client_secret:
        raise ApiloAuthError("Brak Client ID lub Client Secret w konfiguracji.")
    if not config.apilo_auth_code:
        raise ApiloAuthError("Brak kodu autoryzacji (Kod autoryzacji z panelu Apilo).")

    data = _post_token(
        config.apilo_base_url,
        config.apilo_client_id,
        config.apilo_client_secret,
        {"grantType": "authorization_code", "token": config.apilo_auth_code},
    )

    access_token = data.get("accessToken") or data.get("access_token") or ""
    refresh_token = data.get("refreshToken") or data.get("refresh_token") or ""

    if not access_token:
        raise ApiloAuthError(f"Apilo nie zwróciło access_token. Odpowiedź: {data}")

    expires_at = (datetime.now(timezone.utc) + timedelta(days=21)).isoformat()

    config.apilo_access_token = access_token
    config.apilo_refresh_token = refresh_token
    config.apilo_token_expires_at = expires_at
    save_config(config)
    logger.info("Autentykacja Apilo OK — token ważny do %s", expires_at[:10])
    return config


def refresh_access_token(config: AppConfig) -> AppConfig:
    """Odświeżenie access_token za pomocą refresh_token."""
    if not config.apilo_refresh_token:
        raise ApiloAuthError("Brak refresh_token — wymagana ponowna autentykacja.")

    data = _post_token(
        config.apilo_base_url,
        config.apilo_client_id,
        config.apilo_client_secret,
        {"grantType": "refresh_token", "token": config.apilo_refresh_token},
    )

    access_token = data.get("accessToken") or data.get("access_token") or ""
    refresh_token = data.get("refreshToken") or data.get("refresh_token") or config.apilo_refresh_token

    if not access_token:
        raise ApiloAuthError(f"Nie udało się odświeżyć tokena. Odpowiedź: {data}")

    expires_at = (datetime.now(timezone.utc) + timedelta(days=21)).isoformat()

    config.apilo_access_token = access_token
    config.apilo_refresh_token = refresh_token
    config.apilo_token_expires_at = expires_at
    save_config(config)
    logger.info("Token Apilo odświeżony — ważny do %s", expires_at[:10])
    return config


def ensure_valid_token(config: AppConfig) -> AppConfig:
    """Upewnia się, że access_token jest ważny. Odświeża lub re-autentykuje w razie potrzeby."""
    if not config.apilo_access_token:
        return authenticate(config)

    if config.apilo_token_expires_at:
        try:
            expires_at = datetime.fromisoformat(config.apilo_token_expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) + TOKEN_SAFETY_MARGIN < expires_at:
                return config
        except ValueError:
            pass

    # Token wygasł lub wygasa wkrótce
    try:
        return refresh_access_token(config)
    except ApiloAuthError:
        logger.warning("Refresh nie powiódł się — próbuję pełną autentykację")
        return authenticate(config)
