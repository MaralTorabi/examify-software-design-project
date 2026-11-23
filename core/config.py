from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite:///./examify.db"

    # Authentication & Security
    jwt_secret: str = "examify-development-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # Storage & Upload limits
    upload_dir: str = "./storage/private"
    max_pdf_size_bytes: int = 25 * 1024 * 1024  # 25 MB
    max_pages: int = 200

    # AI Subsystem
    offline_mode: bool = False
    ai_provider: str = "mock"
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = "mock-generator"

    @property
    def upload_path(self) -> Path:
        """Returns the resolved upload storage directory."""
        path = Path(self.upload_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    """Returns singleton cached application settings instance."""
    return Settings()
