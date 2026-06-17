"""First-boot bootstrap.

Generates infra secrets (JWT secret, Fernet encryption key) on first run and
persists them to <DATA_DIR>/config.json so they survive container restarts.
This is what lets a package user install with zero environment variables.

User-supplied integration secrets (LLM keys, Google OAuth) are NOT handled here.
Those are entered via the UI and stored encrypted in the DB `credentials` table
using the encryption_key generated below. The database URL is the one pointer
that must live in config.json, because it points AT the DB and cannot live
inside it.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

from src.core.settings import Settings, get_settings


def ensure_bootstrap(settings: Settings, env_file: str | None = ".env") -> Settings:
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = data_dir / "config.json"

    cfg: dict = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except json.JSONDecodeError:
            cfg = {}

    changed = False

    if not settings.jwt_secret and not cfg.get("jwt_secret"):
        cfg["jwt_secret"] = secrets.token_urlsafe(48)
        changed = True

    if not settings.encryption_key and not cfg.get("encryption_key"):
        cfg["encryption_key"] = Fernet.generate_key().decode()
        changed = True

    # Persist the resolved DB url so it is stable across restarts.
    if not cfg.get("DATABASE_URL") and settings.DATABASE_URL:
        cfg["DATABASE_URL"] = settings.DATABASE_URL
        changed = True

    if changed:
        cfg_path.write_text(json.dumps(cfg, indent=2))
        try:
            cfg_path.chmod(0o600)
        except OSError:
            # On Windows, chmod 0o600 might throw an error or do nothing, so we handle it gracefully.
            pass

    # Re-read so freshly written values are picked up by the json source.
    get_settings.cache_clear()
    return get_settings(env_file=env_file)
