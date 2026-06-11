import base64
import hashlib
import secrets
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

CHANNEL_INTEGRATION_KEY = "channel_integration"
SUPPORTED_CHANNELS = {"whatsapp", "messenger", "telegram"}
SECRET_FIELDS: Dict[str, set[str]] = {
    "whatsapp": {"app_secret", "access_token", "verify_token"},
    "messenger": {"app_secret", "page_access_token", "verify_token"},
    "telegram": {"bot_token", "webhook_secret_token"},
}


def _get_fernet() -> Fernet:
    try:
        from src.core.settings import system_setting
    except ImportError as exc:
        raise RuntimeError("Cannot load channel config encryption settings.") from exc

    if not getattr(system_setting, "SECRET_KEY", None):
        raise HTTPException(
            status_code=500,
            detail="SECRET_KEY is required to encrypt and decrypt channel credentials.",
        )

    digest = hashlib.sha256(system_setting.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    try:
        return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return value


def encrypt_channel_config(channel: str, config: Dict[str, Any]) -> Dict[str, Any]:
    if channel not in SUPPORTED_CHANNELS:
        raise HTTPException(status_code=400, detail=f"Unsupported channel: {channel}")

    encrypted: Dict[str, Any] = {}
    secret_fields = SECRET_FIELDS.get(channel, set())
    for key, value in config.items():
        if value is None:
            continue
        if key in secret_fields:
            encrypted[key] = encrypt_value(str(value))
        else:
            encrypted[key] = value
    return encrypted


def decrypt_channel_config(channel: str, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not config:
        return {}
    if channel not in SUPPORTED_CHANNELS:
        raise HTTPException(status_code=400, detail=f"Unsupported channel: {channel}")

    decrypted: Dict[str, Any] = {}
    secret_fields = SECRET_FIELDS.get(channel, set())
    for key, value in config.items():
        if key in secret_fields:
            decrypted[key] = decrypt_value(value)
        else:
            decrypted[key] = value
    return decrypted


def get_channel_config(agent_config: Optional[Dict[str, Any]], channel: str) -> Dict[str, Any]:
    if not agent_config:
        return {}
    raw = agent_config.get(channel)
    return decrypt_channel_config(channel, raw)


def merge_channel_config(agent_config: Optional[Dict[str, Any]], channel: str, raw_values: Dict[str, Any]) -> Dict[str, Any]:
    agent_config = agent_config or {}
    existing = get_channel_config(agent_config, channel)
    merged = {**existing, **raw_values}

    if channel in {"whatsapp", "messenger"} and not merged.get("verify_token"):
        merged["verify_token"] = secrets.token_urlsafe(24)

    if channel == "telegram" and not merged.get("webhook_secret_token"):
        merged["webhook_secret_token"] = secrets.token_urlsafe(24)

    agent_config[channel] = encrypt_channel_config(channel, merged)
    return agent_config


def ensure_channel_tokens(agent_config: Optional[Dict[str, Any]], channel: str) -> Dict[str, Any]:
    agent_config = agent_config or {}
    existing = get_channel_config(agent_config, channel)
    changed = False

    if channel in {"whatsapp", "messenger"} and not existing.get("verify_token"):
        existing["verify_token"] = secrets.token_urlsafe(24)
        changed = True

    if channel == "telegram" and not existing.get("webhook_secret_token"):
        existing["webhook_secret_token"] = secrets.token_urlsafe(24)
        changed = True

    if changed:
        agent_config[channel] = encrypt_channel_config(channel, existing)
    return agent_config


def build_channel_status(agent_config: Optional[Dict[str, Any]], channel: str) -> Dict[str, bool]:
    config = get_channel_config(agent_config, channel)
    if channel == "whatsapp":
        configured = bool(config.get("phone_number_id") and config.get("app_secret") and config.get("access_token"))
        verified = bool(config.get("verified", False))
    elif channel == "messenger":
        configured = bool(config.get("page_id") and config.get("app_secret") and config.get("page_access_token"))
        verified = bool(config.get("verified", False))
    elif channel == "telegram":
        configured = bool(config.get("bot_token") and config.get("webhook_secret_token"))
        verified = bool(config.get("verified", False))
    else:
        configured = False
        verified = False

    return {"configured": configured, "verified": verified}
