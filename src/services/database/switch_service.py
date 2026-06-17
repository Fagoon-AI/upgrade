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

    NOTE on driver: set the URL alembic expects. Since the current project
    uses an ASYNC engine in alembic/env.py, we pass target_url unchanged.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(alembic_ini)
    cfg.set_main_option("sqlalchemy.url", target_url)
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
    cfg["DATABASE_URL"] = target_url
    cfg_path.write_text(json.dumps(cfg, indent=2))
    try:
        cfg_path.chmod(0o600)
    except OSError:
        pass
