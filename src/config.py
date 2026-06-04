"""Application configuration - reads from environment and .env file."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    # Ollama
    ollama_host: str = "http://localhost:11434"
    ollama_main_model: str = "qwen3:8b"
    ollama_light_model: str = "qwen3:4b"

    # Chroma
    chroma_host: str = "localhost"
    chroma_port: int = 8001

    # Application
    xhs_agent_db_path: str = "./data/xhs_agent.db"
    xhs_agent_data_dir: str = "./data"
    xhs_agent_log_level: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.xhs_agent_db_path}"

    @property
    def cases_dir(self) -> Path:
        path = Path(self.xhs_agent_data_dir) / "cases"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def outputs_dir(self) -> Path:
        path = Path(self.xhs_agent_data_dir) / "outputs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def data_dir(self) -> Path:
        return Path(self.xhs_agent_data_dir)


# Global singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
