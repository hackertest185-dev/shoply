"""
core/config.py
Reads all environment variables via Pydantic BaseSettings.
Never import secrets directly — always use settings.SECRET_NAME.
"""
from functools import lru_cache
from urllib.parse import urlparse
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
    PAYMOB_SECRET_KEY: str = ""
    PAYMOB_PUBLIC_KEY: str = ""
    PAYMOB_CARD_INTEGRATION_ID: int = 0
    PAYMOB_HMAC_SECRET: str = ""
    PAYMOB_API_BASE_URL: str = "https://accept.paymob.com"
    PAYMOB_CHECKOUT_URL: str = "https://eg.checkout.paymob.com/"

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
    MAX_REQUEST_BODY_BYTES: int = 16 * 1024 * 1024
    PRODUCT_IMAGE_MAX_BYTES: int = 6 * 1024 * 1024
    DELIVERY_DOCUMENT_MAX_BYTES: int = 10 * 1024 * 1024
    DELIVERY_PROOF_MAX_BYTES: int = 15 * 1024 * 1024

    # ── Legacy Stripe (unused by the storefront) ──────────────────────────────
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # ── AWS S3 ────────────────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_PRODUCTS: str = "shoply-product-images"
    S3_BUCKET_DELIVERY_DOCS: str = "shoply-delivery-docs"
    S3_BUCKET_PROOF: str = "shoply-proof-of-delivery"

    # ── Transactional email ───────────────────────────────────────────────────
    SENDGRID_API_KEY: str = ""
    EMAIL_FROM: str = ""
    EMAIL_FROM_NAME: str = "Shoply"
    FRONTEND_URL: str = "https://shoply-adh.pages.dev"

    # ── Firebase Cloud Messaging ─────────────────────────────────────────────
    # Keep the service-account JSON only in the backend secret store.
    FCM_SERVICE_ACCOUNT_JSON: str = ""

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
    LOGIN_OTP_TTL_SECONDS: int = 300
    LOGIN_OTP_MAX_ATTEMPTS: int = 5

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
        if self.ENABLE_ONLINE_PAYMENTS:
            paymob_required = {
                "PAYMOB_SECRET_KEY": self.PAYMOB_SECRET_KEY,
                "PAYMOB_PUBLIC_KEY": self.PAYMOB_PUBLIC_KEY,
                "PAYMOB_HMAC_SECRET": self.PAYMOB_HMAC_SECRET,
                "PAYMOB_CARD_INTEGRATION_ID": self.PAYMOB_CARD_INTEGRATION_ID,
            }
            missing_paymob = [name for name, value in paymob_required.items() if not str(value).strip() or value == 0]
            if missing_paymob:
                raise RuntimeError(
                    "Online payments require configured Paymob credentials: "
                    + ", ".join(missing_paymob)
                )
            for name, value in (
                ("PAYMOB_API_BASE_URL", self.PAYMOB_API_BASE_URL),
                ("PAYMOB_CHECKOUT_URL", self.PAYMOB_CHECKOUT_URL),
            ):
                parsed = urlparse(value)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise RuntimeError(f"{name} must be a valid HTTPS URL.")
        if self.DEBUG:
            raise RuntimeError("DEBUG must be false in production or staging.")
        if (
            not self.ALLOWED_ORIGINS
            or any(origin.strip() == "*" for origin in self.ALLOWED_ORIGINS)
            or any(
                (parsed := urlparse(origin.strip())).scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                for origin in self.ALLOWED_ORIGINS
            )
        ):
            raise RuntimeError("ALLOWED_ORIGINS must contain explicit HTTPS origins.")
        if self.JWT_ALGORITHM not in {"RS256", "HS256"}:
            raise RuntimeError("JWT_ALGORITHM must be RS256 or HS256.")
        if self.JWT_ALGORITHM == "HS256":
            # HS256 needs one high-entropy shared secret for signing and
            # verification. Distinct 'private/public' values cannot work and
            # short secrets are vulnerable to offline guessing.
            if self.JWT_PRIVATE_KEY != self.JWT_PUBLIC_KEY:
                raise RuntimeError("HS256 requires matching JWT_PRIVATE_KEY and JWT_PUBLIC_KEY values.")
            if len(self.JWT_PRIVATE_KEY.encode("utf-8")) < 32:
                raise RuntimeError("HS256 requires a random secret of at least 32 bytes.")
        else:
            try:
                from cryptography.hazmat.primitives import serialization
                private_key = serialization.load_pem_private_key(
                    self.JWT_PRIVATE_KEY.encode("utf-8"), password=None
                )
                public_key = serialization.load_pem_public_key(
                    self.JWT_PUBLIC_KEY.encode("utf-8")
                )
                if (
                    private_key.key_size < 2048
                    or public_key.key_size < 2048
                    or private_key.public_key().public_numbers() != public_key.public_numbers()
                ):
                    raise ValueError("Invalid RSA key pair")
            except Exception as exc:
                raise RuntimeError("RS256 requires a matching RSA key pair of at least 2048 bits.") from exc
        if self.ADMIN_MFA_REQUIRED and self.ADMIN_MFA_TTL_SECONDS > 900:
            raise RuntimeError("ADMIN_MFA_TTL_SECONDS must be 15 minutes or less.")
        if self.ADMIN_MFA_MAX_ATTEMPTS < 1 or self.ADMIN_MFA_MAX_ATTEMPTS > 10:
            raise RuntimeError("ADMIN_MFA_MAX_ATTEMPTS must be between 1 and 10.")
        if self.LOGIN_OTP_TTL_SECONDS < 60 or self.LOGIN_OTP_TTL_SECONDS > 900:
            raise RuntimeError("LOGIN_OTP_TTL_SECONDS must be between 60 and 900.")
        if self.LOGIN_OTP_MAX_ATTEMPTS < 1 or self.LOGIN_OTP_MAX_ATTEMPTS > 10:
            raise RuntimeError("LOGIN_OTP_MAX_ATTEMPTS must be between 1 and 10.")
        if self.PASSWORD_MIN_LENGTH < 12:
            raise RuntimeError("PASSWORD_MIN_LENGTH must be at least 12.")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
