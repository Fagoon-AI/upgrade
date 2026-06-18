"""Compatibility bridge: workflow code imports 'from src.core.config import settings'."""
from src.core.settings import system_setting as settings  # noqa: F401

__all__ = ["settings"]
