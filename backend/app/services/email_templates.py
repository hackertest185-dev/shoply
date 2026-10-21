"""Table-based transactional email layouts with inline styles and no remote assets."""
import html
from urllib.parse import urlsplit

from app.core.config import settings


def safe_action_url(url: str) -> str:
    """Email buttons may only link to the configured storefront."""
    target, storefront = urlsplit(url), urlsplit(settings.FRONTEND_URL)
    if (
        target.scheme not in {"https", "http"}
        or (target.scheme, target.netloc) != (storefront.scheme, storefront.netloc)
        or target.username or target.password
        or any(char in url for char in "\r\n")
        or (target.scheme == "http" and target.hostname not in {"localhost", "127.0.0.1"})
    ):
        raise ValueError("Email action must point to the storefront")
    return html.escape(url, quote=True)


def text_paragraphs(text: str) -> str:
    return "".join(
        '<p style="margin:0 0 18px;color:#40564e;font-size:15px;line-height:1.8;overflow-wrap:anywhere">'
        + html.escape(paragraph).replace("\n", "<br>") + "</p>"
        for paragraph in text.split("\n\n") if paragraph
    )


def render_email(*, title: str, category: str, preview: str, content: str,
                 action_label: str | None = None, action_url: str | None = None,
                 note: str = "This is a service email from Shoply about your account or order.") -> str:
    """Content is trusted template markup; all variable text must be escaped first."""
    title, category, preview, note = map(html.escape, (title, category, preview, note))
    home = safe_action_url(settings.FRONTEND_URL.rstrip("/") + "/")
    action = ""
    if action_label and action_url:
        href = safe_action_url(action_url)
        action = f'''<table role="presentation" cellpadding="0" cellspacing="0" style="margin:26px 0;width:100%"><tr><td align="center" bgcolor="#dfbd82" style="border-radius:10px;mso-padding-alt:17px 24px"><a href="{href}" style="display:block;padding:17px 24px;color:#112b23;text-decoration:none;font-weight:bold;font-size:15px;border:1px solid #dfbd82;border-radius:10px">{html.escape(action_label)} &rarr;</a></td></tr></table>'''
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light"><title>{title}</title>
<style>@media only screen and (max-width:600px){{.email-outer{{padding:16px 10px!important}}.email-content{{padding:28px 22px!important}}.email-title{{font-size:29px!important}}.email-code{{font-size:34px!important;letter-spacing:8px!important}}}}</style></head>
<body style="margin:0;padding:0;background:#f2f3ee;color:#17392d;font-family:Arial,Helvetica,sans-serif;-webkit-text-size-adjust:100%">
<div style="display:none;font-size:1px;line-height:1px;color:#f2f3ee;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all">{preview}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#f2f3ee"><tr><td class="email-outer" align="center" style="padding:40px 16px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px;border:1px solid #dce3da;border-radius:18px;overflow:hidden;background:#ffffff">
<tr><td bgcolor="#102b23" style="padding:27px 30px;border-bottom:3px solid #dfbd82"><table role="presentation" cellpadding="0" cellspacing="0"><tr><td width="38" height="38" align="center" bgcolor="#dfbd82" style="border-radius:10px;color:#102b23;font-family:Georgia,serif;font-weight:bold;font-size:25px">S</td><td style="padding-left:12px;color:#fff9ee;font-family:Georgia,'Times New Roman',serif;font-size:29px;font-weight:bold">Shoply<span style="color:#dfbd82">.</span></td></tr></table></td></tr>
<tr><td class="email-content" style="padding:38px 36px 32px">
<p style="margin:0 0 14px;color:#82683e;font-size:11px;font-weight:bold;letter-spacing:2px;text-transform:uppercase">{category}</p>
<h1 class="email-title" style="margin:0 0 22px;font-family:Georgia,'Times New Roman',serif;font-size:34px;line-height:1.2;font-weight:normal;color:#16392d">{title}</h1>
{content}{action}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:26px;border-top:1px solid #e7ebe4"><tr><td style="padding-top:20px;color:#738078;font-size:12px;line-height:1.8">{note}</td></tr></table>
</td></tr>
<tr><td bgcolor="#f7f8f3" align="center" style="padding:22px;color:#738078;font-size:12px;line-height:1.8"><a href="{home}" style="color:#285440;text-decoration:none;font-weight:bold">SHOPLY</a><br>Thoughtfully selected. Personally delivered.</td></tr>
</table>
<p style="margin:18px 0 0;color:#8a948c;font-size:11px;line-height:1.6">Sent securely by Shoply &middot; Please never share your sign-in code.</p>
</td></tr></table></body></html>'''
