"""fagoon CLI - a thin wrapper over Docker Compose so package users get an
n8n-like one-command experience without learning Compose.

Install:   pipx install fagoon
Usage:
    fagoon up                       start the stack (lite mode by default)
    fagoon up --full                start with Redis + Celery worker
    fagoon up --ollama              also start the Ollama fallback LLM
    fagoon down                     stop the stack
    fagoon logs [-f]                tail logs
    fagoon config set KEY=VALUE     write to <DATA_DIR>/config.json
    fagoon db set-url URL           repoint the database and run migrations
    fagoon update                   pull the newest pinned image and restart

This wrapper ships its own bundled compose files inside the package so the user
never has to download anything by hand.
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

app = typer.Typer(add_completion=False, help="Fagoon self-hosted control CLI.")

# Compose files are packaged alongside the CLI.
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


@app.command()
def up(
    full: bool = typer.Option(False, "--full", help="Run with Redis + Celery worker."),
    ollama: bool = typer.Option(False, "--ollama", help="Also start the Ollama fallback."),
):
    """Start the Fagoon stack."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    compose_file = COMPOSE_FULL if full else COMPOSE_LITE
    args = [*_compose_bin(), "-f", str(compose_file)]
    if ollama:
        args += ["--profile", "ollama"]
    args += ["up", "-d"]
    env = os.environ.copy()
    env["FAGOON_DATA_DIR"] = str(DATA_DIR)
    typer.secho(f"Starting Fagoon ({'full' if full else 'lite'} mode)...", fg="green")
    _run(args)
    typer.secho("Up. Open http://localhost:8000", fg="green")


@app.command()
def down(full: bool = typer.Option(False, "--full")):
    """Stop the Fagoon stack."""
    compose_file = COMPOSE_FULL if full else COMPOSE_LITE
    _run([*_compose_bin(), "-f", str(compose_file), "down"])


@app.command()
def logs(follow: bool = typer.Option(False, "-f", "--follow")):
    """Show stack logs."""
    args = [*_compose_bin(), "-f", str(COMPOSE_LITE), "logs"]
    if follow:
        args.append("-f")
    _run(args)


config_app = typer.Typer(help="Read/write persisted config.")
app.add_typer(config_app, name="config")


@config_app.command("set")
def config_set(pair: str = typer.Argument(..., help="KEY=VALUE")):
    """Set a config value in <DATA_DIR>/config.json."""
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
    copy_data: bool = typer.Option(False, "--copy-data", help="Also copy existing data."),
):
    """Switch the database via the running app (validates + migrates + restarts)."""
    try:
        r = httpx.post("http://localhost:8000/api/v1/database/switch",
                       json={"url": url, "copy_data": copy_data}, timeout=30)
        if r.status_code == 400:
            typer.secho(f"Rejected: {r.json().get('detail')}", fg="red")
            raise typer.Exit(1)
        r.raise_for_status()
        typer.secho("Switch started. Poll: fagoon db status", fg="green")
    except httpx.ConnectError:
        # Fallback offline path: directly save config if app is not running
        cfg = _load_config()
        cfg["database_url"] = url
        _save_config(cfg)
        typer.secho("App not running. Saved directly to config.json. Start/restart app to apply: fagoon up", fg="yellow")

@db_app.command("status")
def db_status():
    """Show switch progress."""
    try:
        r = httpx.get("http://localhost:8000/api/v1/database/switch/status", timeout=10)
        r.raise_for_status()
        typer.echo(r.text)
    except httpx.ConnectError:
        typer.secho("App not running. Start it first: fagoon up", fg="red")
        raise typer.Exit(1)


@app.command()
def update():
    """Pull the newest pinned image and restart."""
    _run([*_compose_bin(), "-f", str(COMPOSE_LITE), "pull"])
    _run([*_compose_bin(), "-f", str(COMPOSE_LITE), "up", "-d"])
    typer.secho("Updated.", fg="green")


def main():
    app()


if __name__ == "__main__":
    sys.exit(main())
