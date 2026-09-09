"""Configuration de l'application, chargée depuis l'environnement.

Une seule source : les variables d'environnement (voir ``.env.example``). Aucune valeur
secrète par défaut en production — ``FLASH_SECRET_KEY`` doit être fourni.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- général
    env: str = Field(default="development", alias="FLASH_ENV")
    secret_key: str = Field(
        default="dev-insecure-secret-change-me-01234567", alias="FLASH_SECRET_KEY"
    )
    log_level: str = Field(default="INFO", alias="FLASH_LOG_LEVEL")

    # --- API
    api_base_url: str = Field(default="http://localhost:8000", alias="API_BASE_URL")
    cors_allowed_origins: str = Field(default="http://localhost:5173", alias="CORS_ALLOWED_ORIGINS")

    # --- stockage
    database_url: str = Field(
        default="postgresql+psycopg://flash:flash@localhost:5433/flash", alias="DATABASE_URL"
    )
    redis_url: str = Field(default="redis://localhost:6380/0", alias="REDIS_URL")

    # --- JWT
    jwt_access_ttl_seconds: int = Field(default=900, alias="JWT_ACCESS_TTL_SECONDS")
    jwt_refresh_ttl_seconds: int = Field(default=2_592_000, alias="JWT_REFRESH_TTL_SECONDS")

    # --- OTP
    otp_ttl_seconds: int = Field(default=300, alias="OTP_TTL_SECONDS")
    otp_max_attempts: int = Field(default=5, alias="OTP_MAX_ATTEMPTS")
    otp_channel: str = Field(default="console", alias="OTP_CHANNEL")

    # --- notifications
    smtp_host: str = Field(default="localhost", alias="SMTP_HOST")
    smtp_port: int = Field(default=1025, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="Flash <no-reply@flash.local>", alias="SMTP_FROM")
    fcm_credentials_json: str = Field(default="", alias="FCM_CREDENTIALS_JSON")

    # --- KYC
    kyc_document_dir: str = Field(default="/tmp/flash-kyc", alias="KYC_DOCUMENT_DIR")
    admin_api_key: str = Field(default="", alias="ADMIN_API_KEY")

    # --- annulation / remboursement
    reversal_window_seconds: int = Field(default=3_600, alias="REVERSAL_WINDOW_SECONDS")

    # --- carte
    card_webhook_secret: str = Field(default="", alias="CARD_WEBHOOK_SECRET")
    card_daily_limit_minor: int = Field(default=500_000, alias="CARD_DAILY_LIMIT_MINOR")
    card_monthly_limit_minor: int = Field(default=5_000_000, alias="CARD_MONTHLY_LIMIT_MINOR")

    # --- pays par défaut
    default_country: str = Field(default="CI", alias="DEFAULT_COUNTRY")
    default_currency: str = Field(default="XOF", alias="DEFAULT_CURRENCY")

    # --- passerelles externes
    operator_gateway: str = Field(default="sandbox", alias="OPERATOR_GATEWAY")
    card_issuer: str = Field(default="sandbox", alias="CARD_ISSUER")
    bank_gateway: str = Field(default="sandbox", alias="BANK_GATEWAY")

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @field_validator("secret_key")
    @classmethod
    def _minimum_secret_length(cls, value: str) -> str:
        # « prod exige un vrai secret » est revérifié dans create_app (où `env` est fiable).
        if len(value) < 16:
            raise ValueError("FLASH_SECRET_KEY doit faire au moins 16 caractères.")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings"]
