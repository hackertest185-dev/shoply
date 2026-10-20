"""Small Gmail SMTP adapter used for customer email OTPs."""
import asyncio
import html
import smtplib
from email.message import EmailMessage

from app.core.config import settings


def email_is_configured() -> bool:
    return bool(settings.SMTP_USER.strip() and settings.SMTP_PASSWORD.strip())


def _send_sync(recipient: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.EMAIL_FROM or settings.SMTP_USER
    message["To"] = recipient
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(message)


async def send_email_otp(recipient: str, otp: str) -> None:
    if not email_is_configured():
        raise RuntimeError("Email OTP is not configured. Add SMTP_USER and SMTP_PASSWORD.")
    await asyncio.to_thread(
        _send_sync,
        recipient,
        f"Your {settings.EMAIL_FROM_NAME} sign-in code",
        f"Your Shoply sign-in code is {otp}. It expires in {settings.LOGIN_OTP_TTL_SECONDS // 60} minutes.",
        f"<p>Your Shoply sign-in code is:</p><p style='font-size:28px;font-weight:700;letter-spacing:8px'>{html.escape(otp)}</p><p>This code expires in {settings.LOGIN_OTP_TTL_SECONDS // 60} minutes.</p>",
    )


async def send_verification_email(recipient: str, link: str) -> None:
    if not email_is_configured():
        raise RuntimeError("Email verification is not configured.")
    await asyncio.to_thread(
        _send_sync,
        recipient,
        "Verify your Shoply email",
        f"Open this link to verify your Shoply email address. It expires in 24 hours:\n{link}\nIf you did not create an account, ignore this email.",
        f"<p>Verify your Shoply email address to activate your account.</p><p><a href='{html.escape(link, quote=True)}'>Verify email</a></p><p>This link expires in 24 hours. If you did not create an account, ignore this email.</p>",
    )


async def send_order_email(recipient: str, subject: str, text_body: str) -> None:
    if not email_is_configured():
        return
    await asyncio.to_thread(_send_sync, recipient, subject, text_body, f"<p>{html.escape(text_body).replace(chr(10), '<br>')}</p>")
