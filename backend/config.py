"""
Application configuration loaded from environment variables.

Using pydantic-settings instead of os.getenv() because:
1. Type validation: SECRET_KEY missing -> clear error at startup, not 500 mid-request
2. Single source of truth for all config
3. .env file is auto-loaded
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "dev-secret-key-change-in-production-min-32-chars"


class Settings(BaseSettings):
    # Database
    # DATABASE_URL: superuser connection used by Alembic migrations only.
    # APP_DATABASE_URL: non-superuser caseflow_app role used by the running app,
    # so that Postgres RLS policies are enforced. Falls back to DATABASE_URL
    # if not set (e.g., before the RLS migration has run).
    DATABASE_URL: str = "postgresql://caseflow:caseflow_dev@db:5432/caseflow_mb"
    APP_DATABASE_URL: str = ""

    # JWT
    SECRET_KEY: str = _DEV_SECRET
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours

    # AWS (used Day 3)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ca-central-1"
    AWS_S3_BUCKET: str = ""

    # Claude API (used Day 2)
    ANTHROPIC_API_KEY: str = ""

    # Langfuse observability
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # Environment
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Singleton instance imported everywhere config is needed.
settings = Settings()

# Refuse to start in production with the default dev secret key.
# If this fires, set a real SECRET_KEY in the production .env file.
# Generate one with: python -c "import secrets; print(secrets.token_hex(32))"
if settings.ENVIRONMENT == "production" and settings.SECRET_KEY == _DEV_SECRET:
    raise RuntimeError(
        "SECRET_KEY is still set to the default dev value. "
        "Set a real random SECRET_KEY in your production .env before starting."
    )
