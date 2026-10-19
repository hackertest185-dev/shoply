"""Small Gmail SMTP adapter used for customer email OTPs."""
import asyncio
import html
import smtplib
from email.message import EmailMessage

from app.core.config import settings


def email_is_configured() -> bool:
    return bool(settings.SMTP_USER.strip() and settings.SMTP_PASSWORD.strip())


def _send_sync(recipient: str, otp: str) -> None:
    message = EmailMessage()
    message["Subject"] = f"Your {settings.EMAIL_FROM_NAME} verification code"
    message["From"] = settings.EMAIL_FROM or settings.SMTP_USER
    message["To"] = recipient
    message.set_content(
        f"Your Shoply verification code is {otp}. It expires in "
        f"{settings.EMAIL_OTP_TTL_SECONDS // 60} minutes."
    )
    message.add_alternative(
        f"<p>Your Shoply verification code is:</p>"
        f"<p style='font-size:28px;font-weight:700;letter-spacing:8px'>{html.escape(otp)}</p>"
        f"<p>This code expires in {settings.EMAIL_OTP_TTL_SECONDS // 60} minutes.</p>",
        subtype="html",
    )
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(message)


async def send_email_otp(recipient: str, otp: str) -> None:
    if not email_is_configured():
        raise RuntimeError("Email OTP is not configured. Add SMTP_USER and SMTP_PASSWORD.")
    await asyncio.to_thread(_send_sync, recipient, otp)
