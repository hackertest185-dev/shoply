"""Branded multipart service emails over authenticated, certificate-verified SMTP."""
import asyncio
import html
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

from app.core.config import settings
from app.services.email_templates import render_email, safe_action_url, text_paragraphs


def email_is_configured() -> bool:
    return bool(settings.SMTP_USER.strip() and settings.SMTP_PASSWORD.strip())


def _sender_address() -> str:
    smtp_user = settings.SMTP_USER.strip()
    # Personal Gmail must use its authenticated mailbox, not an unverified brand alias.
    if settings.SMTP_HOST.lower() == "smtp.gmail.com" and smtp_user.lower().endswith(("@gmail.com", "@googlemail.com")):
        return smtp_user
    return parseaddr(settings.EMAIL_FROM.strip())[1] or smtp_user


def _send_sync(recipient: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    sender = _sender_address()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.EMAIL_FROM_NAME.strip() or "Shoply", sender))
    message["To"] = recipient
    message["Date"] = formatdate(localtime=False, usegmt=True)
    message["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1])
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(message, from_addr=sender, to_addrs=[recipient])


async def send_email_otp(recipient: str, otp: str) -> None:
    if not email_is_configured():
        raise RuntimeError("Email OTP is not configured. Add SMTP_USER and SMTP_PASSWORD.")
    minutes = settings.LOGIN_OTP_TTL_SECONDS // 60
    content = text_paragraphs("One more step to sign in. Enter this code on the Shoply sign-in screen to securely access your account.")
    content += f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:26px 0;background:#f4f6ef;border:1px solid #dce4d7;border-radius:12px"><tr><td align="center" style="padding:22px 12px"><p style="margin:0 0 12px;color:#738078;font-size:10px;letter-spacing:2px;font-weight:bold">YOUR SIGN-IN CODE</p><div class="email-code" style="font-family:'Courier New',monospace;font-size:40px;letter-spacing:10px;font-weight:bold;color:#17392d">{html.escape(otp)}</div><p style="margin:14px 0 0;color:#738078;font-size:12px">Valid for {minutes} minutes &middot; One use only</p></td></tr></table>'''
    await asyncio.to_thread(
        _send_sync,
        recipient,
        "Your Shoply sign-in code",
        f"Your Shoply sign-in code is {otp}. It expires in {minutes} minutes and can only be used once.\n\nIf you did not try to sign in, do not share this code. You can ignore this email.",
        render_email(title="Your secure sign-in.", category="Account security", preview="Your one-time sign-in code is ready. It expires soon.", content=content,
                     note="Shoply will never ask you to share this code in chat or on WhatsApp. If you did not try to sign in, ignore this email and keep the code private."),
    )


async def send_verification_email(recipient: str, link: str) -> None:
    if not email_is_configured():
        raise RuntimeError("Email verification is not configured.")
    safe_action_url(link)
    hours = settings.EMAIL_VERIFICATION_TTL_SECONDS // 3600
    await asyncio.to_thread(
        _send_sync,
        recipient,
        "Verify your Shoply email",
        f"Welcome to Shoply. Confirm your email to activate your account:\n{link}\n\nThis link expires in {hours} hours and can only be used once. Once verified, sign in with your password and email code.\nIf you did not create an account, ignore this email.",
        render_email(title="Good things start here.", category="Welcome to Shoply", preview="Confirm your email to finish setting up your Shoply account.",
                     content=text_paragraphs(f"Welcome to Shoply. Your account is almost ready. Confirm your email address to make it yours.\n\nThis link is valid for {hours} hours. After confirming, use your email and password to sign in, then enter the code we send you."),
                     action_label="Verify my email", action_url=link,
                     note="If you did not create a Shoply account, you can safely ignore this email. Your email will remain unverified."),
    )


async def send_password_reset_email(recipient: str, link: str) -> None:
    if not email_is_configured():
        raise RuntimeError("Password reset email is not configured.")
    safe_action_url(link)
    await asyncio.to_thread(
        _send_sync, recipient, "Reset your Shoply password",
        f"We received a request to reset your Shoply password. Use this link within 30 minutes:\n{link}\n\nThis link can only be used once. If you did not request this, ignore this email. Your password has not changed.",
        render_email(title="A fresh start, securely.", category="Password recovery", preview="Your secure password reset link is valid for 30 minutes.",
                     content=text_paragraphs("Forgot your password? It happens. Use the button below to choose a new one and get back to your Shoply account.\n\nThis secure link expires in 30 minutes and can only be used once."),
                     action_label="Reset my password", action_url=link,
                     note="If you did not request this, ignore this email. Your password has not changed. Never forward this link to anyone."),
    )


async def send_order_email(recipient: str, subject: str, text_body: str) -> None:
    if not email_is_configured():
        return
    await asyncio.to_thread(
        _send_sync, recipient, subject, text_body,
        render_email(title=subject, category="Your Shoply order", preview="There is an update about your Shoply order.",
                     content=text_paragraphs(text_body), action_label="Open my account",
                     action_url=settings.FRONTEND_URL.rstrip("/") + "/",
                     note="Sign in to your Shoply account to see your orders, messages and available receipts. We will never ask for your password or sign-in code over WhatsApp."),
    )
