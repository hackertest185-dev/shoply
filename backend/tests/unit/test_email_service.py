import ssl
from email.utils import parseaddr
from html.parser import HTMLParser

import pytest

from app.core.config import settings
from app.services import email_service
from app.services.email_templates import safe_action_url


class Links(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.hrefs = []
        self.tags = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "a":
            self.hrefs.append(dict(attrs).get("href"))


@pytest.fixture
def captured_email(monkeypatch):
    messages = []
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://shop.example")
    monkeypatch.setattr(email_service, "email_is_configured", lambda: True)
    monkeypatch.setattr(email_service, "_send_sync", lambda *args: messages.append(args))
    return messages


@pytest.mark.asyncio
async def test_verification_and_reset_have_safe_buttons_and_plain_text(captured_email):
    await email_service.send_verification_email("buyer@example.com", "https://shop.example/#verify_token=example")
    await email_service.send_password_reset_email("buyer@example.com", "https://shop.example/#reset_token=example")
    for message, purpose in zip(captured_email, ("verify_token", "reset_token")):
        _, _, text, markup = message
        target = f"https://shop.example/#{purpose}=example"
        assert target in text
        assert target in Links(markup).hrefs
        assert "<script" not in markup
        assert "<img" not in markup  # branding stays visible when remote images are blocked
        assert "Shoply" in markup


@pytest.mark.asyncio
async def test_signin_code_has_actual_expiry_without_leaking_code_to_preview(captured_email, monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_OTP_TTL_SECONDS", 420)
    await email_service.send_email_otp("buyer@example.com", "012345")
    _, _, text, markup = captured_email[-1]
    assert "012345" in text and "012345" in markup
    assert "7 minutes" in text and "7 minutes" in markup
    assert "one-time sign-in code is ready" in markup


@pytest.mark.asyncio
async def test_chat_and_subject_content_cannot_inject_html(captured_email):
    await email_service.send_order_email("buyer@example.com", '<img src=x onerror="bad()">',
                                         '<script>bad()</script>\n\n<img src=x onerror="bad()">')
    markup = captured_email[-1][3]
    parsed = Links(markup)
    assert "script" not in parsed.tags and "img" not in parsed.tags
    assert "&lt;script&gt;" in markup
    assert all(href.startswith("https://shop.example/") for href in parsed.hrefs)


@pytest.mark.parametrize("target", ["javascript:alert(1)", "https://shop.example.attacker.com/", "https://attacker.com/", "https://shop.example@attacker.com/"])
def test_email_actions_reject_untrusted_urls(target, monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://shop.example")
    with pytest.raises(ValueError):
        safe_action_url(target)


def test_smtp_uses_branded_authenticated_sender_tls_and_multipart(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "SMTP_USER", "shoply.sender@gmail.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "test-only-password")
    monkeypatch.setattr(settings, "EMAIL_FROM", "unverified@other-domain.example")
    monkeypatch.setattr(settings, "EMAIL_FROM_NAME", "Shoply")
    sent = {}

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, *, context):
            assert context.verify_mode == ssl.CERT_REQUIRED
            assert context.check_hostname is True

        def login(self, user, password):
            assert user == settings.SMTP_USER

        def send_message(self, message, **kwargs):
            sent.update(message=message, **kwargs)

    monkeypatch.setattr(email_service.smtplib, "SMTP", SMTP)
    email_service._send_sync("buyer@example.com", "Shoply update", "Plain version", "<p>HTML version</p>")
    message = sent["message"]
    assert parseaddr(message["From"]) == ("Shoply", "shoply.sender@gmail.com")
    assert sent["from_addr"] == "shoply.sender@gmail.com"
    assert sent["to_addrs"] == ["buyer@example.com"]
    assert message["Date"] and message["Message-ID"]
    assert message.get_content_type() == "multipart/alternative"
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == "Plain version"
    assert message.get_body(preferencelist=("html",)).get_content().strip() == "<p>HTML version</p>"
