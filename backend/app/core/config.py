"""Read application settings from environment variables. Secrets belong in a local .env file."""

from functools import lru_cache
from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The credentials currently live in the project-level frontend/.env file.
# Resolve it from this module so the backend can be started from either the
# repository root or backend/ without relying on the shell's working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ENV_FILES = (PROJECT_ROOT / 'frontend' / '.env', PROJECT_ROOT / 'backend' / '.env')

class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    DEEPSEEK_API_KEY: str = ''
    DEEPSEEK_MODEL: str = 'deepseek-chat'
    FRONTEND_ORIGIN: str = Field(
        default='http://localhost:3000',
        validation_alias=AliasChoices('FRONTEND_ORIGIN', 'FRONTEND_URL'),
    )
    MAX_UPLOAD_MB: int = Field(
        default=10,
        validation_alias=AliasChoices('MAX_UPLOAD_MB', 'MAX_UPLOAD_SIZE_MB'),
    )
    CLOUDINARY_CLOUD_NAME: str = ''
    CLOUDINARY_API_KEY: str = ''
    CLOUDINARY_API_SECRET: str = ''
    API_V1_PREFIX: str = '/api/v1'
    model_config = SettingsConfigDict(
        env_file=PROJECT_ENV_FILES,
        extra='ignore',
        populate_by_name=True,
    )

@lru_cache
def get_settings():
    """Return cached application settings loaded from the environment."""
    return Settings()
