"""
Application settings for the WildINTEL Publisher web backend.

Priority order (highest to lowest):
  1. Environment variables                 WILDINTEL_PUBLISHER_WEB_PORT=9000 uvicorn main:app
  2. ~/.config/wildintel_publisher_web/.env   ← config del usuario
  3. <directorio de este módulo>/.env                    ← fallback junto al código

All fields have sensible defaults so the app works out of the box.

Example .env
------------
WILDINTEL_PUBLISHER_WEB_PORT=8767
WILDINTEL_PUBLISHER_WEB_LOG_LEVEL=INFO
WILDINTEL_PUBLISHER_WEB_CORS_ORIGINS=["http://localhost:5174","http://localhost:8767"]
"""
import logging
from pathlib import Path

from platformdirs import user_config_dir
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> tuple[Path, ...]:
    """Return .env search paths in ascending priority order.

    pydantic-settings applies files left-to-right, later files win,
    so the highest-priority location must come last.
    """
    module_dir = Path(__file__).parent
    config_dir = Path(user_config_dir("wildintel_publisher_web"))

    return (
        module_dir / ".env",    # prioridad más baja
        config_dir / ".env",    # prioridad más alta (sobrescribe la anterior)
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_prefix="WILDINTEL_PUBLISHER_WEB_",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
    )

    # ── Server ────────────────────────────────────────────────────────────────
    port: int = 8767
    log_level: str = "INFO"

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list[str] = [
        "http://localhost:5174",
        "http://localhost",
        "http://localhost:8767",
    ]

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, v: str) -> str:
        level = v.upper()
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError(f"Invalid log level: {v!r}")
        return level


settings = Settings()


def configure_logging() -> None:
    """Apply settings.log_level to the root Python logger."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
