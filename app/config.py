"""Configuration module.

This file centralizes runtime configuration for local development and production
deployments (for example on Render). Values can be provided via environment
variables or a local `.env` file.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    app_name: str = "FM TimeTracker"
    environment: str = "development"
    debug: bool = True
    secret_key: str = "change-me-in-production"
    database_url: str = "sqlite:///./fm_timetracker.db"
    host: str = "0.0.0.0"
    port: int = 8000
    secure_cookies: bool = False
    bootstrap_admin_email: str = "admin@change.me"
    bootstrap_admin_password: str = "ChangeMeNow!123"
    secure_bootstrap_onboarding: bool = False
    stripe_secret_key: str | None = None
    stripe_publishable_key: str | None = None

    # Use an absolute path so `.env` is consistently discovered regardless of
    # the process working directory used to start uvicorn/gunicorn.
    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH, env_file_encoding="utf-8")


settings = Settings()
