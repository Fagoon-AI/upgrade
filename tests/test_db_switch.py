"""Tests for the database switch service.

The pure helpers (URL conversion, status I/O, persistence) are tested directly.
The DB-touching checks are tested with a fake asyncpg connection so no live
Postgres is required. An optional live test is included but skipped unless
FAGOON_TEST_PG_URL is set.
"""
from __future__ import annotations

import json
import os

import pytest

from src.services.database import switch_service as svc


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #
def test_to_asyncpg_dsn_strips_sqlalchemy_driver():
    assert svc.to_asyncpg_dsn(
        "postgresql+asyncpg://u:p@host:5432/db"
    ) == "postgresql://u:p@host:5432/db"
    assert svc.to_asyncpg_dsn(
        "postgresql+psycopg://u:p@host/db"
    ) == "postgresql://u:p@host/db"
    # already plain -> unchanged
    assert svc.to_asyncpg_dsn(
        "postgresql://u:p@host/db"
    ) == "postgresql://u:p@host/db"


def test_status_roundtrip(tmp_path):
    s = svc.SwitchStatus(phase=svc.Phase.migrating_schema.value, message="hi",
                         target_host="db.example.com", copy_data=True)
    svc._write_status(str(tmp_path), s)
    back = svc.read_status(str(tmp_path))
    assert back.phase == svc.Phase.migrating_schema.value
    assert back.target_host == "db.example.com"
    assert back.copy_data is True


def test_read_status_defaults_when_missing(tmp_path):
    assert svc.read_status(str(tmp_path)).phase == svc.Phase.idle.value


def test_persist_url_writes_config(tmp_path):
    svc._persist_url(str(tmp_path), "postgresql+asyncpg://u:p@cloud/db")
    cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg["database_url"] == "postgresql+asyncpg://u:p@cloud/db"


def test_persist_url_preserves_existing_config(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"jwt_secret": "keep-me"}))
    svc._persist_url(str(tmp_path), "postgresql://u:p@cloud/db")
    cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg["jwt_secret"] == "keep-me"           # not clobbered
    assert cfg["database_url"] == "postgresql://u:p@cloud/db"


# --------------------------------------------------------------------------- #
# pgvector check with a fake connection
# --------------------------------------------------------------------------- #
class _FakeConn:
    def __init__(self, available=True, installed=False, can_create=True):
        self._available = available
        self._installed = installed
        self._can_create = can_create
        self.closed = False

    async def fetchval(self, q, *a):
        if "pg_available_extensions" in q:
            return 1 if self._available else None
        if "pg_extension" in q:
            return 1 if self._installed else None
        return 1

    async def execute(self, q, *a):
        if "CREATE EXTENSION" in q and not self._can_create:
            import asyncpg
            raise asyncpg.InsufficientPrivilegeError("no")
        return "OK"

    async def close(self):
        self.closed = True


@pytest.fixture
def patch_connect(monkeypatch):
    """Patch asyncpg.connect to return a chosen fake connection."""
    def _install(conn):
        async def _connect(*a, **k):
            return conn
        import asyncpg
        monkeypatch.setattr(asyncpg, "connect", _connect)
    return _install


@pytest.mark.asyncio
async def test_pgvector_ok_when_installable(patch_connect):
    patch_connect(_FakeConn(available=True, installed=False, can_create=True))
    await svc.ensure_pgvector("postgresql://u:p@h/db")  # no raise


@pytest.mark.asyncio
async def test_pgvector_ok_when_already_installed(patch_connect):
    patch_connect(_FakeConn(available=True, installed=True))
    await svc.ensure_pgvector("postgresql://u:p@h/db")  # no raise


@pytest.mark.asyncio
async def test_pgvector_unavailable_raises(patch_connect):
    patch_connect(_FakeConn(available=False))
    with pytest.raises(svc.PgVectorUnavailable):
        await svc.ensure_pgvector("postgresql://u:p@h/db")


@pytest.mark.asyncio
async def test_pgvector_privilege_error_raises(patch_connect):
    patch_connect(_FakeConn(available=True, installed=False, can_create=False))
    with pytest.raises(svc.InsufficientPrivilege):
        await svc.ensure_pgvector("postgresql://u:p@h/db")


# --------------------------------------------------------------------------- #
# optional live integration test
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_live_validate_and_pgvector():
    url = os.environ.get("FAGOON_TEST_PG_URL")
    if not url:
        pytest.skip("set FAGOON_TEST_PG_URL to a pgvector-capable Postgres to run")
    await svc.validate_connection(url)
    await svc.ensure_pgvector(url)
