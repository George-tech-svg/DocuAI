"""Read application settings from environment variables. Secrets belong in a local .env file."""

from functools import lru_cache
from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

# The credentials currently live in the project-level frontend/.env file.
# Resolve it from this module so the backend can be started from either the
# repository root or backend/ without relying on the shell's working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ENV_FILES = (PROJECT_ROOT / 'frontend' / '.env', PROJECT_ROOT / 'backend' / '.env')
MAX_SAFE_UPLOAD_MB = 20
MAX_SAFE_EXTRACTED_CHARS = 5_000_000

class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    DEEPSEEK_API_KEY: str = ''
    DEEPSEEK_MODEL: str = 'deepseek-flash'
    FRONTEND_ORIGIN: str = Field(
        default='https://docuai-jet.vercel.app',
        validation_alias=AliasChoices('FRONTEND_ORIGIN', 'FRONTEND_URL'),
    )
    FRONTEND_ORIGINS: str = ''
    MAX_UPLOAD_MB: int = Field(
        # Keep uploads within the configured Vercel function request limit.
        default=20,
        validation_alias=AliasChoices('MAX_UPLOAD_MB', 'MAX_UPLOAD_SIZE_MB'),
    )
    MAX_EXTRACTED_CHARS: int = Field(default=MAX_SAFE_EXTRACTED_CHARS, gt=0)
    CLOUDINARY_CLOUD_NAME: str = ''
    CLOUDINARY_API_KEY: str = ''
    CLOUDINARY_API_SECRET: str = ''
    MPESA_ENVIRONMENT: str = 'sandbox'
    MPESA_CONSUMER_KEY: str = ''
    MPESA_CONSUMER_SECRET: str = ''
    MPESA_SHORTCODE: str = ''
    MPESA_PASSKEY: str = ''
    MPESA_CALLBACK_BASE_URL: str = ''
    MPESA_TRANSACTION_TYPE: str = 'CustomerPayBillOnline'
    SUBSCRIPTIONS_ENFORCED: bool = False
    ADMIN_BOOTSTRAP_CODE: str = ''
    GOOGLE_CLIENT_ID: str = ''
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


def max_upload_mb() -> int:
    """Apply a conservative per-file cap even if hosting env is oversized."""
    return 10


def max_extracted_chars() -> int:
    """Apply a bounded extracted-text cap to protect function memory and time."""
    return min(get_settings().MAX_EXTRACTED_CHARS, MAX_SAFE_EXTRACTED_CHARS)


def psycopg_database_url(database_url: str) -> str:
    """Select the installed Psycopg 3 driver regardless of SQLAlchemy version."""
    url = make_url(database_url)
    if url.drivername in {'postgres', 'postgresql'}:
        url = url.set(drivername='postgresql+psycopg')
    return url.render_as_string(hide_password=False)
