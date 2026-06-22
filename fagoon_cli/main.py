"""Fagoon CLI - Self-hosted AI platform control.

Install:   pipx install fagoon-upgrade
Usage:
    fagoon up                       Start the stack (lite mode by default)
    fagoon up --full                Start with Redis + Celery worker
    fagoon up --ollama              Start with local Ollama LLM
    fagoon down                     Stop the stack
    fagoon logs [-f]                Tail logs
    fagoon config set KEY=VALUE     Write to <DATA_DIR>/config.json
    fagoon db set-url URL           Repoint the database and run migrations
    fagoon update                   Pull the newest pinned image and restart

The CLI ships bundled Docker Compose files so users get a one-command
experience without managing compose files manually.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import typer

app = typer.Typer(add_completion=False, help="Fagoon - Self-hosted AI Platform CLI.")

PKG_DIR = Path(__file__).resolve().parent
COMPOSE_LITE = PKG_DIR / "compose" / "docker-compose.yml"
COMPOSE_FULL = PKG_DIR / "compose" / "docker-compose.full.yml"

DATA_DIR = Path(os.environ.get("FAGOON_DATA_DIR", Path.home() / ".fagoon"))
CONFIG_PATH = DATA_DIR / "config.json"


def _compose_bin() -> list[str]:
    if shutil.which("docker") is None:
        typer.secho("Docker is not installed or not on PATH.", fg="red")
        raise typer.Exit(1)
    return ["docker", "compose"]


def _run(args: list[str]) -> None:
    typer.secho("$ " + " ".join(args), fg="bright_black")
    result = subprocess.run(args)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_config(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    try:
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass


def _get_fernet(cfg: dict):
    from cryptography.fernet import Fernet
    key = cfg.get("ENCRYPTION_KEY")
    if not key:
        key = Fernet.generate_key().decode()
        cfg["ENCRYPTION_KEY"] = key
    return Fernet(key.encode())


def _encrypt_val(cfg: dict, val: str) -> str:
    if not val or val.startswith("fernet:"):
        return val
    f = _get_fernet(cfg)
    return "fernet:" + f.encrypt(val.encode()).decode()


def _decrypt_val(cfg: dict, val: str) -> str:
    if not val or not val.startswith("fernet:"):
        return val
    try:
        f = _get_fernet(cfg)
        return f.decrypt(val[7:].encode()).decode()
    except Exception:
        return val


@app.command()
def up(
    full: bool = typer.Option(False, "--full", help="Run with Redis + Celery worker."),
    ollama: bool = typer.Option(False, "--ollama", help="Start with Ollama local LLM."),
    skip_setup: bool = typer.Option(False, "--skip-setup", help="Skip first-time setup prompt."),
):
    """Start the Fagoon platform."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing config
    cfg = _load_config()

    # Migrate .env if it exists and hasn't been migrated
    env_path = Path(".env")
    if env_path.exists() and not cfg.get("_env_migrated"):
        typer.secho("Found local .env file. Migrating sensitive keys to config.json...", fg="cyan")
        from cryptography.fernet import Fernet
        
        # Ensure we have an encryption key
        if not cfg.get("ENCRYPTION_KEY"):
            cfg["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    k = k.strip().upper()
                    v = v.strip().strip("'\"")
                    if v:
                        # Encrypt sensitive keys
                        if any(s in k.lower() for s in ("key", "secret", "password", "token")):
                            cfg[k] = _encrypt_val(cfg, v)
                        else:
                            cfg[k] = v
        cfg["_env_migrated"] = True
        _save_config(cfg)
        typer.secho("Migration complete.", fg="green")

    # First-time setup: check if config exists
    is_first_run = not cfg.get("_setup_done")

    if is_first_run and not skip_setup:
        typer.secho("")
        typer.secho("  Welcome to Fagoon!", fg="green", bold=True)
        typer.secho("  Let's set up your AI platform.", fg="cyan")
        typer.secho("")

        # Ask about LLM provider
        typer.secho("  How would you like to power your AI?", fg="white", bold=True)
        typer.secho("  1) I have an API key (OpenAI, Gemini, Groq, etc.)", fg="white")
        typer.secho("  2) Use local Ollama model (free, runs on your machine)", fg="white")
        typer.secho("  3) Skip for now (configure later in the UI)", fg="white")
        typer.secho("")

        choice = typer.prompt("  Choose [1/2/3]", default="3")

        if choice == "1":
            typer.secho("")
            typer.secho("  Which provider?", fg="white", bold=True)
            typer.secho("  a) OpenAI", fg="white")
            typer.secho("  b) Gemini (Google)", fg="white")
            typer.secho("  c) Groq", fg="white")
            typer.secho("  d) Anthropic", fg="white")
            provider = typer.prompt("  Choose [a/b/c/d]", default="b")

            key = typer.prompt("  Enter your API key", hide_input=True)

            provider_map = {"a": "OPENAI_API_KEY", "b": "GEMINI_API_KEY", "c": "GROQ_API_KEY", "d": "ANTHROPIC_API_KEY"}
            env_key = provider_map.get(provider, "GEMINI_API_KEY")
            cfg[env_key] = key
            typer.secho(f"  Saved {env_key}.", fg="green")

        elif choice == "2":
            ollama = True
            cfg["OLLAMA_BASE_URL"] = "http://ollama:11434"
            cfg["FALLBACK_MODEL_PROVIDER"] = "ollama"
            typer.secho("")
            typer.secho("  Which model size? (smaller = faster download, less RAM)", fg="white", bold=True)
            typer.secho("  a) Tiny   (~1.5GB) - qwen2.5:1.5b    - basic tasks", fg="white")
            typer.secho("  b) Small  (~2GB)   - llama3.2:latest  - recommended", fg="white")
            typer.secho("  c) Medium (~4GB)   - gemma2:2b        - better quality", fg="white")
            typer.secho("  d) Custom - enter your own model name", fg="white")
            model_choice = typer.prompt("  Choose [a/b/c/d]", default="b")

            model_map = {
                "a": "qwen2.5:1.5b",
                "b": "llama3.2:latest",
                "c": "gemma2:2b",
            }
            if model_choice == "d":
                custom_model = typer.prompt("  Enter model name (e.g. mistral:latest)")
                cfg["FALLBACK_MODEL_NAME"] = custom_model.strip()
            else:
                cfg["FALLBACK_MODEL_NAME"] = model_map.get(model_choice, "llama3.2:latest")

            typer.secho(f"  Model: {cfg['FALLBACK_MODEL_NAME']}", fg="green")
            typer.secho("  Will be pulled automatically on first startup.", fg="cyan")

        else:
            typer.secho("  No worries! Configure your LLM provider in the UI after login.", fg="yellow")

        cfg["_setup_done"] = True
        _save_config(cfg)
        typer.secho("")

    compose_file = COMPOSE_FULL if full else COMPOSE_LITE
    args = [*_compose_bin(), "-f", str(compose_file)]
    if ollama:
        args += ["--profile", "ollama"]
    args += ["up", "-d"]

    env = os.environ.copy()
    env["FAGOON_DATA_DIR"] = str(DATA_DIR)

    # Pass saved config as env vars to compose
    cfg = _load_config()

    # Generate EVOLUTION_API_KEY if missing
    if not cfg.get("EVOLUTION_API_KEY"):
        import secrets
        raw_key = secrets.token_hex(16)
        cfg["EVOLUTION_API_KEY"] = _encrypt_val(cfg, raw_key)
        _save_config(cfg)
        typer.secho("Generated and encrypted EVOLUTION_API_KEY for WhatsApp gateway.", fg="blue")

    for key in ["OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY",
                "JWT_SECRET", "ENCRYPTION_KEY", "OLLAMA_BASE_URL", "EVOLUTION_API_KEY", "DATABASE_URL"]:
        val = cfg.get(key)
        if val:
            env[key] = _decrypt_val(cfg, val)
    mode = "full" if full else "lite"
    typer.secho(f"Starting Fagoon ({mode} mode)...", fg="green")
    _run(args)
    typer.secho("", fg="green")
    typer.secho("  Fagoon is running!", fg="green", bold=True)
    typer.secho("  Frontend:  http://localhost:3000", fg="cyan")
    typer.secho("  Backend:   http://localhost:8000", fg="cyan")
    typer.secho("", fg="green")


@app.command()
def down(full: bool = typer.Option(False, "--full")):
    """Stop the Fagoon platform."""
    compose_file = COMPOSE_FULL if full else COMPOSE_LITE
    _run([*_compose_bin(), "-f", str(compose_file), "down"])
    typer.secho("Fagoon stopped.", fg="yellow")


@app.command()
def logs(follow: bool = typer.Option(False, "-f", "--follow")):
    """Show platform logs."""
    args = [*_compose_bin(), "-f", str(COMPOSE_LITE), "logs"]
    if follow:
        args.append("-f")
    _run(args)


@app.command()
def status():
    """Check if Fagoon is running."""
    try:
        r = httpx.get("http://localhost:8000/openapi.json", timeout=5)
        if r.status_code == 200:
            typer.secho("Fagoon is running.", fg="green")
            typer.secho("  Frontend:  http://localhost:3000", fg="cyan")
            typer.secho("  Backend:   http://localhost:8000", fg="cyan")
        else:
            typer.secho(f"Backend responded with {r.status_code}", fg="yellow")
    except httpx.ConnectError:
        typer.secho("Fagoon is not running. Start with: fagoon up", fg="red")


config_app = typer.Typer(help="Manage platform configuration.")
app.add_typer(config_app, name="config")


@config_app.command("set")
def config_set(pair: str = typer.Argument(..., help="KEY=VALUE")):
    """Set a config value."""
    if "=" not in pair:
        typer.secho("Expected KEY=VALUE", fg="red")
        raise typer.Exit(1)
    key, value = pair.split("=", 1)
    cfg = _load_config()
    cfg[key.strip()] = value.strip()
    _save_config(cfg)
    typer.secho(f"Set {key.strip()}.", fg="green")


@config_app.command("show")
def config_show():
    """Print current config (secrets redacted)."""
    cfg = _load_config()
    redacted = {
        k: ("***" if any(s in k.lower() for s in ("secret", "key", "password")) else v)
        for k, v in cfg.items()
    }
    typer.echo(json.dumps(redacted, indent=2))


db_app = typer.Typer(help="Database management.")
app.add_typer(db_app, name="db")


@db_app.command("set-url")
def db_set_url(
    url: str = typer.Argument(..., help="postgresql+asyncpg://..."),
    copy_data: bool = typer.Option(False, "--copy-data", help="Copy existing data to new DB."),
):
    """Switch the database (validates, migrates, restarts)."""
    try:
        r = httpx.post("http://localhost:8000/api/v1/database/switch",
                       json={"url": url, "copy_data": copy_data}, timeout=30)
        if r.status_code == 400:
            typer.secho(f"Rejected: {r.json().get('detail')}", fg="red")
            raise typer.Exit(1)
        r.raise_for_status()
        typer.secho("Database switch started. Check: fagoon db status", fg="green")
    except httpx.ConnectError:
        cfg = _load_config()
        cfg["database_url"] = url
        _save_config(cfg)
        typer.secho("Platform not running. Saved to config. Start with: fagoon up", fg="yellow")


@db_app.command("status")
def db_status():
    """Show database switch progress."""
    try:
        r = httpx.get("http://localhost:8000/api/v1/database/switch/status", timeout=10)
        r.raise_for_status()
        typer.echo(r.text)
    except httpx.ConnectError:
        typer.secho("Platform not running. Start with: fagoon up", fg="red")
        raise typer.Exit(1)


@app.command()
def update():
    """Pull the newest image and restart."""
    typer.secho("Updating Fagoon...", fg="cyan")
    _run([*_compose_bin(), "-f", str(COMPOSE_LITE), "pull"])
    _run([*_compose_bin(), "-f", str(COMPOSE_LITE), "up", "-d"])
    typer.secho("Updated successfully.", fg="green")


def main():
    app()


if __name__ == "__main__":
    sys.exit(main())
