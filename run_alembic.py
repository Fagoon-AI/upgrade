#!/usr/bin/env python
"""
Helper script to run Alembic with safe env defaults.
This avoids Settings() crashing due to missing required env vars.

Usage:
    python run_alembic.py revision --autogenerate -m "description"
    python run_alembic.py upgrade head
    python run_alembic.py downgrade -1
"""
import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load .env if it exists
env_file = Path(".env")
if env_file.exists():
    load_dotenv(env_file)

# Set safe defaults for required env vars if not already set
env_defaults = {
    "DATABASE_URL": os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost/fagoon_dev"),
    "JWT_SECRET": os.getenv("JWT_SECRET", "dev-secret-key"),
    "JWT_ALGORITHM": os.getenv("JWT_ALGORITHM", "HS256"),
    "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID", "dummy"),
    "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET", "dummy"),
    "GOOGLE_REDIRECT_URI": os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:3000"),
    "EMAIL_HOST": os.getenv("EMAIL_HOST", "localhost"),
    "EMAIL_PORT": os.getenv("EMAIL_PORT", "587"),
    "EMAIL_USERNAME": os.getenv("EMAIL_USERNAME", "dummy"),
    "EMAIL_PASSWORD": os.getenv("EMAIL_PASSWORD", "dummy"),
    "EMAIL_FROM": os.getenv("EMAIL_FROM", "noreply@fagoon.ai"),
    "GCS_BUCKET_NAME": os.getenv("GCS_BUCKET_NAME", "dummy"),
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", "dummy"),
    "VIDEO_STORAGE_PATH": os.getenv("VIDEO_STORAGE_PATH", "/tmp/videos"),
    "CELERY_BROKER_URL": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    "CELERY_RESULT_BACKEND": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
    "SECRET_KEY": os.getenv("SECRET_KEY", "dev-secret"),
    "FAGOON_URL": os.getenv("FAGOON_URL", "http://localhost:3000"),
    "DEFAULT_URL": os.getenv("DEFAULT_URL", "http://localhost:3000"),
    "SERPER_API_KEY": os.getenv("SERPER_API_KEY", "dummy"),
    "SERPAPI_API_KEY": os.getenv("SERPAPI_API_KEY", "dummy"),
    "COOKIE_DOMAIN_1": os.getenv("COOKIE_DOMAIN_1", "localhost"),
    "COOKIE_DOMAIN_2": os.getenv("COOKIE_DOMAIN_2", "localhost"),
    "COOKIE_DOMAIN_3": os.getenv("COOKIE_DOMAIN_3", "localhost"),
}

# Apply defaults
for key, value in env_defaults.items():
    if key not in os.environ:
        os.environ[key] = value

# Run Alembic with provided arguments
alembic_cmd = [".venv\\Scripts\\alembic.exe" if sys.platform == "win32" else ".venv/bin/alembic"] + sys.argv[1:]
result = subprocess.run(alembic_cmd, cwd=Path(__file__).parent)
sys.exit(result.returncode)
