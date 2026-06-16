# Fagoon Database Switch — Implementation Guide

Lets a user move from the bundled local Postgres to their own external Postgres
URL, the n8n way. **You host no database.** Default install runs the bundled
local DB; the user optionally switches to their cloud DB from a settings screen.

The design guarantees that matter:
- The **local DB is never touched** until the target is proven good, and is left
  intact afterward as a fallback. A failed switch loses nothing.
- **pgvector is verified on the target BEFORE migrating** — your RAG needs it, so
  a target without it fails fast with a clear message instead of half-migrating.
- "Migrate" is two distinct things and the UI must say which: **schema only**
  (fresh start, default) vs **schema + data copy** (optional). One button that
  silently does schema-only is a data-loss surprise.
- The connection pool can't hot-swap, so a switch ends with a **restart**.

> Hand this file to Gemini CLI like the others. Create the files, make the
> cross-file edits in the "Wiring & other files" section, then run the tests.

---

## Phase 1 — The switch service

All the logic lives here: validation, the pgvector preflight, schema migration,
optional data copy, config persistence, and the restart trigger. Each step writes
to a status file in `DATA_DIR` (a file, not the DB — because we may be migrating
the DB itself).

**Create `src/services/database/__init__.py`:** empty package marker.

**Create `src/services/database/switch_service.py`:**

````python
"""Database switch service.

Moves a Fagoon instance from its bundled local Postgres to a user-supplied
external Postgres URL. Order is chosen so the LOCAL DB is never touched until the
target is proven good, and is left intact afterwards as a fallback.

Steps (each updates a status file the UI/CLI can poll):
    1. validate  - can we connect to the target with the given role?
    2. pgvector  - is the `vector` extension available, and can we enable it?
    3. preflight - can the role create/drop tables (needed for migrations)?
    4. schema    - alembic upgrade head against the target
    5. data      - OPTIONAL: pg_dump (data only) local -> pg_restore into target
    6. persist   - write the new database_url to config.json
    7. restart   - flag restart_required (pool can't hot-swap); optionally self-exit

Status lives in <DATA_DIR>/db_switch_status.json (a FILE, not the DB, because we
may be migrating the DB itself). Single-process lite mode makes this safe.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# errors
# --------------------------------------------------------------------------- #
class SwitchError(Exception):
    """Base for switch failures; message is safe to show the user."""


class PgVectorUnavailable(SwitchError):
    pass


class InsufficientPrivilege(SwitchError):
    pass


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #
class Phase(str, Enum):
    idle = "idle"
    validating = "validating"
    checking_pgvector = "checking_pgvector"
    preflight = "preflight"
    migrating_schema = "migrating_schema"
    migrating_data = "migrating_data"
    persisting = "persisting"
    completed = "completed"
    failed = "failed"


@dataclass
class SwitchStatus:
    phase: str = Phase.idle.value
    message: str = ""
    target_host: str = ""
    copy_data: bool = False
    restart_required: bool = False
    error: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def _status_path(data_dir: str) -> Path:
    return Path(data_dir) / "db_switch_status.json"


def read_status(data_dir: str) -> SwitchStatus:
    try:
        raw = json.loads(_status_path(data_dir).read_text())
        return SwitchStatus(**raw)
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return SwitchStatus()


def _write_status(data_dir: str, status: SwitchStatus) -> None:
    p = _status_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(status.to_json())


# --------------------------------------------------------------------------- #
# url helpers
# --------------------------------------------------------------------------- #
def to_asyncpg_dsn(url: str) -> str:
    """SQLAlchemy URL -> plain libpq DSN for asyncpg / pg_dump."""
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def _host_of(url: str) -> str:
    dsn = to_asyncpg_dsn(url)
    try:
        return dsn.split("@", 1)[1].split("/", 1)[0]
    except IndexError:
        return "unknown"


# --------------------------------------------------------------------------- #
# individual checks (kept small + testable)
# --------------------------------------------------------------------------- #
async def validate_connection(target_url: str) -> None:
    import asyncpg

    dsn = to_asyncpg_dsn(target_url)
    try:
        conn = await asyncpg.connect(dsn, timeout=10)
    except Exception as e:  # noqa: BLE001
        raise SwitchError(f"Cannot connect to the target database: {e}") from e
    try:
        await conn.fetchval("SELECT 1")
    finally:
        await conn.close()


async def ensure_pgvector(target_url: str) -> None:
    """Confirm the `vector` extension is available and enabled on the target.
    Raises PgVectorUnavailable / InsufficientPrivilege with a user-facing fix."""
    import asyncpg

    dsn = to_asyncpg_dsn(target_url)
    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        available = await conn.fetchval(
            "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
        )
        if not available:
            raise PgVectorUnavailable(
                "The target database does not offer the 'vector' (pgvector) "
                "extension. Use a Postgres provider/image that bundles pgvector "
                "(Supabase, Neon, RDS, Cloud SQL, Azure all support it)."
            )
        installed = await conn.fetchval(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
        )
        if installed:
            return
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except asyncpg.InsufficientPrivilegeError as e:
            raise InsufficientPrivilege(
                "pgvector is available but your role cannot enable it. Enable it "
                "once as a superuser/owner (CREATE EXTENSION vector) or via your "
                "provider's console, then retry."
            ) from e
    finally:
        await conn.close()


async def preflight_write(target_url: str) -> None:
    """Confirm the role can create/drop tables (needed by migrations)."""
    import asyncpg

    dsn = to_asyncpg_dsn(target_url)
    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        await conn.execute("CREATE TABLE IF NOT EXISTS _fagoon_preflight (id int)")
        await conn.execute("DROP TABLE IF EXISTS _fagoon_preflight")
    except asyncpg.InsufficientPrivilegeError as e:
        raise InsufficientPrivilege(
            "Your role cannot create tables on the target database. Grant it "
            "CREATE/USAGE on the schema, then retry."
        ) from e
    finally:
        await conn.close()


def run_alembic_upgrade(target_url: str, alembic_ini: str = "alembic.ini") -> None:
    """Run migrations against an arbitrary target. Blocking; call in a thread.

    NOTE on driver: set the URL alembic expects. If your alembic env.py uses an
    async engine, pass the asyncpg URL; if sync, pass a psycopg URL. Adjust the
    `url_for_alembic` line below to match your env.py.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(alembic_ini)
    # Most alembic setups want a SYNC url. If yours is async, replace with target_url.
    url_for_alembic = target_url.replace("+asyncpg", "+psycopg")
    cfg.set_main_option("sqlalchemy.url", url_for_alembic)
    command.upgrade(cfg, "head")


def copy_data(source_url: str, target_url: str) -> None:
    """OPTIONAL data migration: pg_dump (data only) from source, restore to target.
    Requires postgresql-client (pg_dump/pg_restore) in the image, version >= the
    source server major version. Schema must already exist on the target (run
    run_alembic_upgrade first). Blocking; call in a thread.
    """
    source_dsn = to_asyncpg_dsn(source_url)
    target_dsn = to_asyncpg_dsn(target_url)
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as tmp:
        dump_path = tmp.name
    try:
        dump = subprocess.run(
            ["pg_dump", "-Fc", "--data-only", "--no-owner", "--no-privileges",
             "-d", source_dsn, "-f", dump_path],
            capture_output=True, text=True,
        )
        if dump.returncode != 0:
            raise SwitchError(f"pg_dump failed: {dump.stderr.strip()[:500]}")
        restore = subprocess.run(
            ["pg_restore", "--data-only", "--no-owner", "--no-privileges",
             "--disable-triggers", "-d", target_dsn, dump_path],
            capture_output=True, text=True,
        )
        # pg_restore can emit non-fatal warnings on stderr with rc!=0; surface them
        if restore.returncode != 0:
            raise SwitchError(f"pg_restore failed: {restore.stderr.strip()[:500]}")
    finally:
        try:
            os.unlink(dump_path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
async def perform_switch(
    *,
    target_url: str,
    source_url: str,
    data_dir: str,
    copy_existing_data: bool,
    allow_self_restart: bool,
    alembic_ini: str = "alembic.ini",
) -> None:
    """Run the full switch. Updates the status file at each step. Never raises
    out of the background task; failures land in status.error with local DB
    untouched."""
    status = SwitchStatus(
        target_host=_host_of(target_url),
        copy_data=copy_existing_data,
    )

    def step(phase: Phase, message: str) -> None:
        status.phase = phase.value
        status.message = message
        _write_status(data_dir, status)
        log.info("db switch: %s - %s", phase.value, message)

    try:
        step(Phase.validating, "Connecting to the target database")
        await validate_connection(target_url)

        step(Phase.checking_pgvector, "Checking the pgvector extension")
        await ensure_pgvector(target_url)

        step(Phase.preflight, "Verifying write privileges")
        await preflight_write(target_url)

        step(Phase.migrating_schema, "Creating the schema on the target")
        await asyncio.to_thread(run_alembic_upgrade, target_url, alembic_ini)

        if copy_existing_data:
            step(Phase.migrating_data, "Copying existing data to the target")
            await asyncio.to_thread(copy_data, source_url, target_url)

        step(Phase.persisting, "Saving the new database URL")
        _persist_url(data_dir, target_url)

        status.restart_required = True
        step(Phase.completed, "Switch complete. A restart is required to apply it.")

        if allow_self_restart:
            # Let the response flush, then exit so Docker's restart policy reboots
            # us against the new DB. Requires `restart: unless-stopped` in compose.
            asyncio.get_event_loop().call_later(2.0, lambda: os.kill(os.getpid(), signal.SIGTERM))

    except SwitchError as e:
        status.phase = Phase.failed.value
        status.error = str(e)
        status.message = "Switch failed. Your local database is unchanged."
        _write_status(data_dir, status)
        log.warning("db switch failed: %s", e)
    except Exception as e:  # noqa: BLE001
        status.phase = Phase.failed.value
        status.error = f"Unexpected error: {e}"
        status.message = "Switch failed. Your local database is unchanged."
        _write_status(data_dir, status)
        log.exception("db switch crashed")


def _persist_url(data_dir: str, target_url: str) -> None:
    cfg_path = Path(data_dir) / "config.json"
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except json.JSONDecodeError:
            cfg = {}
    cfg["database_url"] = target_url
    cfg_path.write_text(json.dumps(cfg, indent=2))
    cfg_path.chmod(0o600)
````

---

## Phase 2 — The admin-only endpoints

Quick synchronous validation returns obvious errors immediately; the heavy
migration runs in the background and the UI polls for status.

**Create `src/api/v1/routers/database/__init__.py`:** empty package marker.

**Create `src/api/v1/routers/database/db_switch.py`:**

````python
"""Database switch endpoints.

POST /api/v1/database/switch        - validate quickly, then run migration in bg
GET  /api/v1/database/switch/status - poll progress

ADMIN ONLY. Wire your existing auth/admin dependency into `require_admin`. On an
internet-exposed instance this endpoint must never be reachable by a non-owner,
since it can repoint the whole datastore.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from src.services.database import switch_service as svc

router = APIRouter(prefix="/api/v1/database", tags=["database"])


# Replace this stub with your real admin dependency.
async def require_admin(request: Request):
    # e.g. user = request.state.user; if not user.is_admin: raise HTTPException(403)
    return True


class SwitchRequest(BaseModel):
    url: str
    copy_data: bool = False

    @field_validator("url")
    @classmethod
    def _looks_like_pg(cls, v: str) -> str:
        if not v.startswith(("postgresql://", "postgresql+asyncpg://", "postgresql+psycopg://")):
            raise ValueError("URL must be a PostgreSQL connection string.")
        return v


@router.post("/switch", status_code=202, dependencies=[Depends(require_admin)])
async def start_switch(body: SwitchRequest, request: Request):
    settings = request.app.state.settings

    # Quick synchronous validation so obvious errors return immediately (not as
    # a background failure). Connection + pgvector are fast.
    try:
        await svc.validate_connection(body.url)
        await svc.ensure_pgvector(body.url)
    except svc.SwitchError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Source is the currently-active DB (the bundled local one on first switch).
    source_url = settings.database_url or settings.database_url_default

    # Run the heavy part in the background. Single-process lite mode => asyncio
    # task is fine. (Don't route through Celery: this is rare, admin-only, and
    # must run in the web process that will self-restart.)
    asyncio.create_task(
        svc.perform_switch(
            target_url=body.url,
            source_url=source_url,
            data_dir=settings.data_dir,
            copy_existing_data=body.copy_data,
            allow_self_restart=getattr(settings, "allow_self_restart", False),
        )
    )
    return {
        "status": "started",
        "copy_data": body.copy_data,
        "poll": "/api/v1/database/switch/status",
    }


@router.get("/switch/status", dependencies=[Depends(require_admin)])
async def switch_status(request: Request):
    settings = request.app.state.settings
    status = svc.read_status(settings.data_dir)
    return status.__dict__
````

---

## Phase 3 — Tests

Mocked so they need no live Postgres; one optional live test runs only when
`FAGOON_TEST_PG_URL` is set.

**Create `tests/test_db_switch.py`:**

````python
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
````

Run them:

```bash
uv run pytest tests/test_db_switch.py -q
```

---

## Wiring & other files (the cross-file changes you asked for)

These touch files that already exist. Map of every change:

### A. `Dockerfile` — add the Postgres client (ONLY needed for data copy)
`pg_dump`/`pg_restore` must be present and their major version must be **>= the
source server** (the bundled DB is pg16, so install client 16). Debian slim's
default repo doesn't carry 16, so add the PGDG repo:

```dockerfile
# add near the top of deploy/Dockerfile, before COPY . .
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates gnupg lsb-release wget \
    && wget -qO /usr/share/keyrings/pgdg.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.asc] http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*
```

If you only ever support **fresh-start** (no data copy), you can skip this — schema
migration uses Alembic, which is already a Python dependency. Add the client only
when you enable the data-copy path.

### B. `src/core/settings.py` — one new field
```python
class Settings(BaseSettings):
    ...
    allow_self_restart: bool = False   # if true, app SIGTERMs itself after a switch
```
Self-restart only works behind a restart policy (next item). Leave it `false` and
restart manually, or set it `true` for a hands-off switch.

### C. `deploy/docker-compose.yml` (and `.full.yml`) — restart policy + reachability
- The `app` service needs `restart: unless-stopped` so a self-restart (or a crash)
  comes back up. (Your compose already has this — confirm it stays.)
- The container needs **network egress to the target DB host** (cloud Postgres).
  Default Docker bridge egress covers this; no change unless you run a locked-down
  egress policy, in which case allow the DB host/port.
- The bundled local DB stays exactly as is — it remains the source for a data copy
  and the fallback after a switch.

### D. `src/launch_server.py` — register the router
```python
from src.api.v1.routers.database import db_switch
app.include_router(db_switch.router)
```

### E. `src/api/v1/routers/database/db_switch.py` — wire real admin auth
Replace the `require_admin` stub with your actual admin dependency (the same
owner/admin gate from the hardening guide). This endpoint repoints the entire
datastore; it must be owner-only, especially on an internet-exposed instance.

### F. `alembic` — confirm the driver the service passes
`run_alembic_upgrade` sets `sqlalchemy.url` and converts `+asyncpg` → `+psycopg`
because most alembic env.py files use a **sync** engine. If your `alembic/env.py`
runs an **async** engine instead, change that one line in `run_alembic_upgrade`
to pass `target_url` unchanged. Also ensure Alembic is initialized and your
migrations are committed (the entrypoint already runs `alembic upgrade head` on
boot, so this should already hold).

### G. `fagoon_cli/main.py` — make `db set-url` drive the API, add status
The CLI command should call the running app's endpoint (so validation + migration
run with app context) rather than only writing the file. Add a status command:

```python
import httpx

@db_app.command("set-url")
def db_set_url(
    url: str = typer.Argument(...),
    copy_data: bool = typer.Option(False, "--copy-data", help="Also copy existing data."),
):
    """Switch the database via the running app (validates + migrates + restarts)."""
    try:
        r = httpx.post("http://localhost:8000/api/v1/database/switch",
                       json={"url": url, "copy_data": copy_data}, timeout=30)
        if r.status_code == 400:
            typer.secho(f"Rejected: {r.json().get('detail')}", fg="red"); raise typer.Exit(1)
        r.raise_for_status()
        typer.secho("Switch started. Poll: fagoon db status", fg="green")
    except httpx.ConnectError:
        typer.secho("App not running. Start it first: fagoon up", fg="red"); raise typer.Exit(1)

@db_app.command("status")
def db_status():
    """Show switch progress."""
    r = httpx.get("http://localhost:8000/api/v1/database/switch/status", timeout=10)
    typer.echo(r.text)
```
(Keep your earlier file-writing `set-url` only as an offline, fresh-start path if
you want; the API path is the real one because it validates and migrates.)

---

## The switch sequence (what actually happens, in order)

1. **validate** — connect to the target with the given role.
2. **pgvector** — confirm `vector` is available; enable it; clear error if the
   role can't (told to enable as owner / via provider console).
3. **preflight** — confirm the role can create/drop tables.
4. **schema** — `alembic upgrade head` on the target.
5. **data** *(optional)* — `pg_dump --data-only` source → `pg_restore` target.
6. **persist** — write `database_url` to `config.json` (other config preserved).
7. **restart** — flag `restart_required`; self-exit if `allow_self_restart`,
   else the user runs `fagoon down && fagoon up`.

If any step before persist fails, the local DB is untouched and `status.error`
explains why. The local DB is **not deleted** on success — keep it until the user
confirms the new DB works.

---

## UI guidance (so "migrate" isn't a surprise)

Offer two clearly-labeled choices on the database screen:
- **"Switch to external database (start fresh)"** → `copy_data: false`. Schema
  only; existing chats/agents/workflows stay in the old DB.
- **"Migrate to external database (copy my data)"** → `copy_data: true`. Runs the
  pg_dump/restore. Warn it can take a while for large data and that the instance
  restarts at the end.

Show the polled status phase (validating → pgvector → schema → data → done) so the
user sees progress, and surface `status.error` verbatim on failure.

---

## Caveats to keep in mind

- **pgvector on the target is mandatory.** The check enforces it; just make the
  error visible in the UI. Managed providers support it but often require enabling
  it once with appropriate privileges.
- **pg_dump version** must be ≥ the source server major version (16). The
  Dockerfile change installs client 16.
- **Data copy edge cases:** very large datasets are slow; `--data-only` restore
  relies on the schema existing (it does, from step 4) and on dependency ordering
  (custom-format pg_restore handles FK order). Test with representative data.
- **Self-restart needs a restart policy.** Without `restart: unless-stopped`, a
  self-exit just stops the app. Default to manual restart unless you've confirmed
  the policy.
- **Admin-only, always.** This endpoint can move all data; gate it behind the
  owner account.

---

## Verification checklist

- [ ] `uv run pytest tests/test_db_switch.py -q` passes (9 passed, 1 skipped).
- [ ] Router registered in `launch_server.py`; `require_admin` wired to real auth.
- [ ] Dockerfile installs `postgresql-client-16` (if data copy enabled).
- [ ] `allow_self_restart` field added to settings.
- [ ] `app` service has `restart: unless-stopped`.
- [ ] alembic driver line in `run_alembic_upgrade` matches your env.py (sync/async).
- [ ] Manual end-to-end: point at a real cloud Postgres with pgvector, run a
      fresh-start switch, confirm restart + the app comes up on the new DB.
- [ ] Repeat with `--copy-data` against a populated local DB; confirm rows landed.
- [ ] Negative test: point at a Postgres WITHOUT pgvector; confirm it fails at the
      pgvector step with local DB untouched.
