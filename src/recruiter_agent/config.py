"""Environment-driven settings. Model string is configurable; keys stay out of git."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ORIGINS = (
    "https://vasubansal1033.github.io,"
    "http://localhost:4321,"
    "http://127.0.0.1:4321"
)

# Caps match the /chat contract.
MAX_QUESTION_CHARS = 2000
MAX_JD_CHARS = 12000
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW_S = 60

# AGENT_MODEL prefix → Settings field. ollama needs no key.
_PROVIDER_KEY_ATTR = {
    "gemini": "gemini_api_key",
    "anthropic": "anthropic_api_key",
    "openai": "openai_api_key",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    agent_model: str = Field(
        default="gemini/gemini-2.5-flash",
        validation_alias="AGENT_MODEL",
    )
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    anthropic_api_key: str | None = Field(
        default=None, validation_alias="ANTHROPIC_API_KEY"
    )
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    ollama_api_base: str = Field(
        default="http://localhost:11434",
        validation_alias="OLLAMA_API_BASE",
    )
    openai_agents_disable_tracing: str = Field(
        default="1",
        validation_alias="OPENAI_AGENTS_DISABLE_TRACING",
    )
    allowed_origins: str = Field(
        default=_DEFAULT_ORIGINS,
        validation_alias="ALLOWED_ORIGINS",
    )
    port: int = Field(default=8000, validation_alias="PORT")
    profile_dir: Path | None = Field(default=None, validation_alias="PROFILE_DIR")

    @property
    def origins_list(self) -> list[str]:
        return [s.strip() for s in self.allowed_origins.split(",") if s.strip()]

    @property
    def resolved_profile_dir(self) -> Path:
        if self.profile_dir is not None:
            return Path(self.profile_dir)
        return _REPO_ROOT / "profile"

    @property
    def api_key_for_model(self) -> str | None:
        """Key for the AGENT_MODEL prefix. Unknown prefix or ollama → None."""
        prefix = self.agent_model.lower().split("/", 1)[0]
        attr = _PROVIDER_KEY_ATTR.get(prefix)
        if attr is None:
            return None
        return _present(getattr(self, attr))

    @property
    def is_configured(self) -> bool:
        """Ollama needs no cloud key; Gemini/Anthropic/OpenAI do."""
        model = self.agent_model.lower()
        if model.startswith("ollama/"):
            return True
        return self.api_key_for_model is not None


def _present(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _apply_tracing_default(settings: Settings) -> None:
    """Keep Agents SDK tracing off unless the user already set the env var."""
    os.environ.setdefault(
        "OPENAI_AGENTS_DISABLE_TRACING",
        settings.openai_agents_disable_tracing or "1",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    _apply_tracing_default(settings)
    return settings


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
