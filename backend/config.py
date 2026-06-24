"""
Application configuration loaded from environment variables.

Using pydantic-settings instead of os.getenv() because:
1. Type validation: SECRET_KEY missing -> clear error at startup, not 500 mid-request
2. Single source of truth for all config
3. .env file is auto-loaded
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    # Default uses Docker service name 'db' because this project is Docker-first.
    # docker-compose.yml's env var overrides this; local non-Docker dev would use localhost.
    DATABASE_URL: str = "postgresql://caseflow:caseflow_dev@db:5432/caseflow_mb"

    # JWT (used in Day 1 Step 3)
    SECRET_KEY: str = "dev-secret-key-change-in-production-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours for dev convenience

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
