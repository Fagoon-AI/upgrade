import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# ensure project root is importable
sys.path.insert(0, os.path.abspath(os.getcwd()))

# Set safe defaults for required env vars BEFORE importing system_setting
# This avoids Settings() crashes due to missing environment variables during alembic runs
_env_defaults = {
    "JWT_SECRET": "alembic-dev-secret",
    "JWT_ALGORITHM": "HS256",
    "GOOGLE_CLIENT_ID": "alembic-dummy",
    "GOOGLE_CLIENT_SECRET": "alembic-dummy",
    "GOOGLE_REDIRECT_URI": "http://localhost:3000",
    "EMAIL_HOST": "localhost",
    "EMAIL_PORT": "587",
    "EMAIL_USERNAME": "dummy",
    "EMAIL_PASSWORD": "dummy",
    "EMAIL_FROM": "noreply@fagoon.ai",
    "GCS_BUCKET_NAME": "alembic-dummy",
    "GEMINI_API_KEY": "alembic-dummy",
    "VIDEO_STORAGE_PATH": "/tmp/videos",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/1",
    "SECRET_KEY": "alembic-dev-secret",
    "FAGOON_URL": "http://localhost:3000",
    "DEFAULT_URL": "http://localhost:3000",
    "SERPER_API_KEY": "dummy",
    "SERPAPI_API_KEY": "dummy",
    "COOKIE_DOMAIN_1": "localhost",
    "COOKIE_DOMAIN_2": "localhost",
    "COOKIE_DOMAIN_3": "localhost",
}
for key, value in _env_defaults.items():
    if key not in os.environ:
        os.environ[key] = value

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

# Import your project's metadata object for 'autogenerate' support
from src.models.sql.base import Base  # noqa: E402
from src.core.settings import system_setting  # noqa: E402

target_metadata = Base.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = system_setting.DATABASE_URL or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    """Run migrations in 'online' mode using an async engine."""
    url = system_setting.DATABASE_URL or config.get_main_option("sqlalchemy.url")
    connectable = create_async_engine(url, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def main():
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        asyncio.run(run_migrations_online())


if __name__ == "__main__":
    main()
