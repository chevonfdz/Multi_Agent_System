"""Application settings, read from environment variables and the optional .env file."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
CATEGORIES = ("food", "clothes", "electronics")


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    data_dir: Path = BASE_DIR / "data"
    log_dir: Path = BASE_DIR / "logs"
    frontend_dir: Path = BASE_DIR / "frontend"
    websites_file: Path = BASE_DIR / "config" / "websites.yaml"

    jwt_secret: str = ""
    token_hours: int = 24

    llm_provider: str = "none"          # "none" (rule-based) or "anthropic"
    llm_model: str = "claude-opus-5-5"
    llm_timeout_seconds: float = 30.0

    agent_timeout_seconds: float = 10.0
    history_context_messages: int = 10
    results_per_category: int = 5

    enable_scheduler: bool = True
    scrape_hour: int = 0
    scrape_minute: int = 0
    timezone: str = ""                  # empty = the computer's local time zone
    scrape_on_startup: str = "if_empty"  # "if_empty", "always" or "never"
    request_delay_seconds: float = 1.0
    user_agent: str = "MultiAgentShopBot/1.0 (student project)"

    host: str = "127.0.0.1"
    port: int = 8000
    categories: tuple[str, ...] = field(default=CATEGORIES)

    @property
    def app_db_path(self) -> Path:
        return self.data_dir / "app.db"

    def product_db_path(self, category: str) -> Path:
        return self.data_dir / f"{category}.db"

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        load_dotenv(env_file or BASE_DIR / ".env", override=False)
        data_dir = Path(_env("DATA_DIR", str(BASE_DIR / "data")))
        settings = cls(
            data_dir=data_dir,
            log_dir=Path(_env("LOG_DIR", str(BASE_DIR / "logs"))),
            websites_file=Path(_env("WEBSITES_FILE", str(BASE_DIR / "config" / "websites.yaml"))),
            jwt_secret=_env("JWT_SECRET"),
            token_hours=_env_int("TOKEN_HOURS", 24),
            llm_provider=_env("LLM_PROVIDER", "none").lower(),
            llm_model=_env("LLM_MODEL", "claude-opus-5-5"),
            llm_timeout_seconds=_env_float("LLM_TIMEOUT_SECONDS", 30.0),
            agent_timeout_seconds=_env_float("AGENT_TIMEOUT_SECONDS", 10.0),
            history_context_messages=_env_int("HISTORY_CONTEXT_MESSAGES", 10),
            results_per_category=_env_int("RESULTS_PER_CATEGORY", 5),
            enable_scheduler=_env_bool("ENABLE_SCHEDULER", True),
            scrape_hour=_env_int("SCRAPE_HOUR", 0),
            scrape_minute=_env_int("SCRAPE_MINUTE", 0),
            timezone=_env("TIMEZONE"),
            scrape_on_startup=_env("SCRAPE_ON_STARTUP", "if_empty").lower(),
            request_delay_seconds=_env_float("REQUEST_DELAY_SECONDS", 1.0),
            host=_env("HOST", "127.0.0.1"),
            port=_env_int("PORT", 8000),
        )
        settings.prepare()
        return settings

    def prepare(self) -> None:
        """Create folders and make sure a JWT secret exists."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        if not self.jwt_secret or self.jwt_secret.startswith("change-me"):
            self.jwt_secret = self._load_or_create_secret()

    def _load_or_create_secret(self) -> str:
        # No secret configured: keep a random one in data/ so logins survive restarts.
        secret_file = self.data_dir / ".jwt_secret"
        if secret_file.exists():
            existing = secret_file.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        secret = secrets.token_urlsafe(48)
        secret_file.write_text(secret, encoding="utf-8")
        return secret
