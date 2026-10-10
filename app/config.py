import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    webhook_secret: str = field(default_factory=lambda: _env("WEBHOOK_SECRET", "change-me"))
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: _env("ANTHROPIC_MODEL", "claude-haiku-5-5"))
    db_path: str = field(default_factory=lambda: _env("DB_PATH", "leads.db"))
    sinks: tuple[str, ...] = field(
        default_factory=lambda: tuple(s.strip() for s in _env("SINKS", "console").split(",") if s.strip())
    )
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
