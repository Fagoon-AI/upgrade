import os
from typing import Any, Annotated, List, Optional
from pydantic import AnyUrl, BeforeValidator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    FRONTEND_HOST: str = "*"

    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Fagoon Agents Workflow"
    API_SWAGGER_PATH: str = "/upgrade/0329032"
    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [self.FRONTEND_HOST]

    ALLOWED_CORS_ORIGIN: List[str] = [
        "http://localhost:3000",
        "https://develop-upgrade.fagoon.ai",
        "https://upgrade.fagoon.ai",
        "http://0.0.0.0:2321",
        "http://localhost:8000", # new added
    ]

    # LLM Related Configuration
    OPENAI_API_KEY: str = None
    GROQ_API_KEY: str = None
    HUGGINGFACE_API_KEY: str = None
    ELEVENLABS_API_KEY: str = None
    GOOGLE_API_KEY: str = None
    ANTHROPIC_API_KEY: str = None

    # PostgreSQL Connection
    DATABASE_URL: str

    # External APIs

    GROQ_MODEL_NAME: str = "llama3-8b-8192"

    # Google OAuth Settings
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    FRONTEND_REDIRECT_URI: str = "http://localhost:3000"

    GOOGLE_AUTH_SCOPES: list[str] = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/spreadsheets",
    ]

    # Video related configs
    GCS_BUCKET_NAME: str
    GEMINI_API_KEY: str
    VIDEO_STORAGE_PATH: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    SECRET_KEY: str
    LOG_LEVEL: str = "INFO"
    ENABLE_VEO_GENERATION: bool = True
    MAX_VEO_GENERATIONS_PER_JOB: int = 15
    MAX_VEO_VIDEO_DURATION_SECONDS: int = 5
    MOCK_VEO_API_IF_DISABLED: bool = True

    # Upgrade Authentication
    JWT_SECRET: str
    JWT_EXPIRES_IN: str = "90d"
    JWT_ALGORITHM: str
    JWT_COOKIE_EXPIRES_IN_DAYS: int = 90
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Cookie Domain Settings
    COOKIE_DOMAIN_1: str
    COOKIE_DOMAIN_2: str
    COOKIE_DOMAIN_3: str
    # Email Settings
    EMAIL_HOST: str
    EMAIL_PORT: int
    EMAIL_USERNAME: str
    EMAIL_PASSWORD: str
    EMAIL_FROM: str

    FAGOON_URL: str
    DEFAULT_URL: str
    SERPER_API_KEY: str
    SERPAPI_API_KEY: str
    FAL_KEY: str = None
    FAST_MODEL_PROVIDER: str = "groq"
    FAST_MODEL_ID: str = "llama3-8b-8192"

    SMART_MODEL_PROVIDER: str = "openai"
    SMART_MODEL_ID: str = "gpt-4o"

    # Channel webhook / integration configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    WEBHOOK_VERIFY_TOKEN: Optional[str] = None
    WHATSAPP_APP_SECRET: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    FACEBOOK_APP_SECRET: Optional[str] = None
    FACEBOOK_PAGE_ACCESS_TOKEN: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_BOT_SECRET_TOKEN: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True, env_file_encoding='utf-8', case_sensitive=False, override=True)

    @staticmethod
    def get_value(key: str) -> str:
        """Fetches the value of an environment variable by key."""
        return os.getenv(key)

## Get the setting via function call (Singleton Instance Created to reduce making multiple instance)
system_setting = Settings()
