"""Typed settings read from the environment (and `.env` when no env is injected)."""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, model_validator


class Settings(BaseModel):
    llm_provider: Literal["ollama", "groq"] = "ollama"
    llm_model: str = "qwen2.5:3b"
    embed_model: str = "bge-m3"
    ollama_host: str = "http://localhost:11434"
    kb_dir: Path = Path("kb.example")
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/talk_to_my_cv"

    @property
    def chat_model(self) -> str:
        """The model that writes answers, for the selected provider."""
        return self.groq_model if self.llm_provider == "groq" else self.llm_model

    @model_validator(mode="after")
    def _groq_needs_a_key(self) -> "Settings":
        if self.llm_provider == "groq" and not self.groq_api_key:
            raise ValueError("LLM_PROVIDER=groq needs GROQ_API_KEY (set it in .env)")
        return self


def read_env() -> dict[str, str]:
    """`.env` overlaid with the process environment (the process wins)."""
    return {k: v for k, v in {**dotenv_values(".env"), **os.environ}.items() if v is not None}


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build settings from `env`; by default, `.env` overlaid with the process environment."""
    if env is None:
        env = read_env()
    fields = {name: env[name.upper()] for name in Settings.model_fields if env.get(name.upper())}
    return Settings(**fields)
