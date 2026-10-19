"""
core/config.py
Reads all environment variables via Pydantic BaseSettings.
Never import secrets directly — always use settings.SECRET_NAME.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    APP_NAME: str = "Shoply E-Commerce API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"  # production | staging | development
    ENABLE_LEGACY_DELIVERY: bool = False
    ENABLE_ONLINE_PAYMENTS: bool = False

    # ── Server ───────────────────────────────────────────────────────────────
    PORT: int = 8000
    ALLOWED_ORIGINS: list[str] = [
        "https://shoply.com",
        "https://www.shoply.com",
    ]

    # ── MongoDB ───────────────────────────────────────────────────────────────
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "shoply"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"

    # ── JWT (RS256 — loaded from AWS Secrets Manager in production) ───────────
    # In dev, provide PEM strings directly via .env
    JWT_PRIVATE_KEY: str = ""   # RS256 private key PEM
    JWT_PUBLIC_KEY: str = ""    # RS256 public key PEM
    JWT_ALGORITHM: str = "RS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ADMIN_MFA_REQUIRED: bool = True
    ADMIN_MFA_TTL_SECONDS: int = 300
    ADMIN_MFA_MAX_ATTEMPTS: int = 5
    ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES: int = 10
    ADMIN_REFRESH_TOKEN_EXPIRE_DAYS: int = 1
    PASSWORD_MIN_LENGTH: int = 12
    MAX_REQUEST_BODY_BYTES: int = 12 * 1024 * 1024
    PRODUCT_IMAGE_MAX_BYTES: int = 6 * 1024 * 1024
    DELIVERY_DOCUMENT_MAX_BYTES: int = 10 * 1024 * 1024
    DELIVERY_PROOF_MAX_BYTES: int = 15 * 1024 * 1024

    # ── Stripe ────────────────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # ── AWS S3 ────────────────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_PRODUCTS: str = "shoply-product-images"
    S3_BUCKET_DELIVERY_DOCS: str = "shoply-delivery-docs"
    S3_BUCKET_PROOF: str = "shoply-proof-of-delivery"

    # ── Email (SendGrid) ──────────────────────────────────────────────────────
    SENDGRID_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@shoply.com"
    EMAIL_FROM_NAME: str = "Shoply"
    FRONTEND_URL: str = "https://shoply-adh.pages.dev"

    # ── Gmail SMTP (email OTP) ───────────────────────────────────────────────
    # Use a Gmail App Password here, never the normal Gmail password.
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # ── OTP ───────────────────────────────────────────────────────────────────
    OTP_TTL_SECONDS: int = 600          # 10 minutes
    OTP_MAX_ATTEMPTS: int = 3           # per order per window
    OTP_LOCK_SECONDS: int = 600         # 10-minute lock after exhaustion
    EMAIL_OTP_TTL_SECONDS: int = 600
    EMAIL_OTP_MAX_ATTEMPTS: int = 5
    EMAIL_VERIFICATION_TTL_SECONDS: int = 24 * 60 * 60

    # ── Rate limits (used in slowapi decorators) ──────────────────────────────
    RATE_LIMIT_LOGIN: str = "5/15minute"
    RATE_LIMIT_REGISTER: str = "3/hour"
    RATE_LIMIT_REFRESH: str = "10/15minute"
    RATE_LIMIT_FORGOT_PASSWORD: str = "3/hour"
    RATE_LIMIT_DEFAULT: str = "60/minute"

    def validate_runtime(self) -> None:
        """Fail fast when a production deployment is missing critical secrets."""
        if self.ENVIRONMENT not in {"production", "staging"}:
            return
        required = {
            "MONGO_URI": self.MONGO_URI,
            "REDIS_URL": self.REDIS_URL,
            "JWT_PRIVATE_KEY": self.JWT_PRIVATE_KEY,
            "JWT_PUBLIC_KEY": self.JWT_PUBLIC_KEY,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise RuntimeError(
                "Missing required production settings: " + ", ".join(missing)
            )
        if self.DEBUG:
            raise RuntimeError("DEBUG must be false in production or staging.")
        if (
            not self.ALLOWED_ORIGINS
            or any(origin.strip() == "*" for origin in self.ALLOWED_ORIGINS)
            or any(not origin.strip().startswith("https://") for origin in self.ALLOWED_ORIGINS)
        ):
            raise RuntimeError("ALLOWED_ORIGINS must contain explicit HTTPS origins.")
        if self.ADMIN_MFA_REQUIRED and self.ADMIN_MFA_TTL_SECONDS > 900:
            raise RuntimeError("ADMIN_MFA_TTL_SECONDS must be 15 minutes or less.")
        if self.ADMIN_MFA_MAX_ATTEMPTS < 1 or self.ADMIN_MFA_MAX_ATTEMPTS > 10:
            raise RuntimeError("ADMIN_MFA_MAX_ATTEMPTS must be between 1 and 10.")
        if self.PASSWORD_MIN_LENGTH < 12:
            raise RuntimeError("PASSWORD_MIN_LENGTH must be at least 12.")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
