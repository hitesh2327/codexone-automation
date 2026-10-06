"""Outgoing email: a small nodemailer-style sender on top of the standard library (smtplib).

    transport = create_transport()                    # like nodemailer.createTransport({...})
    transport.send(Message(to=..., subject=..., text=..., html=...))

Configuration comes from the environment (.env locally, SSM on AWS), read when a mail is sent:

    MAIL_DRIVER      smtp | console   default: smtp when SMTP_HOST is set, otherwise console
    SMTP_HOST        e.g. smtp.gmail.com, smtp.sendgrid.net, email-smtp.us-east-1.amazonaws.com
    SMTP_PORT        587 (STARTTLS) or 465 (SSL). Default 587.
    SMTP_SECURE      starttls | ssl | none. Default: ssl on port 465, otherwise starttls.
    SMTP_USER / SMTP_PASS
    MAIL_FROM        sender address, e.g. no-reply@yourdomain.com
    MAIL_FROM_NAME   display name, default "Content admin"

The console driver prints the whole email (including one-time codes) to the log instead of sending it.
It exists so the flows can be demoed and developed with no mail server; use `smtp` for real users.
"""
from __future__ import annotations

import html
import logging
import smtplib
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from src.config import get_env, load_brand

log = logging.getLogger("codexone.api.mail")


class MailError(RuntimeError):
    """The email could not be handed to the mail server."""


@dataclass
class Message:
    to: str
    subject: str
    text: str
    html: str | None = None


# --------------------------------------------------------------------------- #
# Transports
# --------------------------------------------------------------------------- #
class ConsoleTransport:
    name = "console"

    def send(self, msg: Message) -> None:
        bar = "=" * 64
        log.info("\n%s\n[mail:console] To: %s\n[mail:console] Subject: %s\n\n%s\n%s", bar, msg.to, msg.subject,
                 msg.text, bar)
        # Also drop it in data/outbox/ so a demo can open the "email" without digging through logs.
        try:
            out = Path(get_env("MAIL_OUTBOX_DIR", required=False) or "data/outbox")
            out.mkdir(parents=True, exist_ok=True)
            body = f"To: {msg.to}\nSubject: {msg.subject}\n\n{msg.text}"
            (out / f"{time.strftime('%Y%m%d-%H%M%S')}-{msg.to.replace('@', '_at_')}.txt").write_text(body, encoding="utf-8")
            (out / "latest.txt").write_text(body, encoding="utf-8")
            if msg.html:
                (out / "latest.html").write_text(msg.html, encoding="utf-8")
        except OSError:
            pass  # read-only filesystem etc.: the log line above is enough


class SmtpTransport:
    name = "smtp"

    def __init__(self, host: str, port: int, secure: str, user: str | None, password: str | None,
                 sender: str, sender_name: str) -> None:
        self.host, self.port, self.secure = host, port, secure
        self.user, self.password = user, password
        self.sender, self.sender_name = sender, sender_name

    def _build(self, msg: Message) -> EmailMessage:
        em = EmailMessage()
        em["From"] = formataddr((self.sender_name, self.sender))
        em["To"] = msg.to
        em["Subject"] = msg.subject
        em["Date"] = formatdate(localtime=False)
        em["Message-ID"] = make_msgid(domain=self.sender.rsplit("@", 1)[-1])
        em.set_content(msg.text)
        if msg.html:
            em.add_alternative(msg.html, subtype="html")
        return em

    def _connect(self) -> smtplib.SMTP:
        ctx = ssl.create_default_context()
        if self.secure == "ssl":
            return smtplib.SMTP_SSL(self.host, self.port, timeout=15, context=ctx)
        smtp = smtplib.SMTP(self.host, self.port, timeout=15)
        smtp.ehlo()
        if self.secure == "starttls":
            smtp.starttls(context=ctx)
            smtp.ehlo()
        return smtp

    def send(self, msg: Message, retries: int = 2) -> None:
        em = self._build(msg)
        last: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                with self._connect() as smtp:
                    if self.user:
                        smtp.login(self.user, self.password or "")
                    smtp.send_message(em)
                log.info("mail sent to %s via %s:%s", msg.to, self.host, self.port)
                return
            except smtplib.SMTPAuthenticationError as e:  # wrong credentials: retrying can't help
                raise MailError("The mail server rejected the SMTP username or password.") from e
            except smtplib.SMTPRecipientsRefused as e:
                raise MailError("The mail server refused the recipient address.") from e
            except (smtplib.SMTPException, OSError) as e:
                last = e
                log.warning("mail attempt %d/%d failed: %s", attempt, retries, e)
                if attempt < retries:
                    time.sleep(1.5 * attempt)
        raise MailError("Couldn't reach the mail server.") from last


def create_transport() -> ConsoleTransport | SmtpTransport:
    user = (get_env("SMTP_USER", required=False) or get_env("SMTP_USERNAME", required=False) or "").strip()
    password = (get_env("SMTP_PASS", required=False) or get_env("SMTP_PASSWORD", required=False) or "").strip()
    sender_name = (get_env("MAIL_FROM_NAME", required=False) or get_env("SMTP_NAME", required=False, default="Content admin") or "Content admin").strip()
    
    host = (get_env("SMTP_HOST", required=False) or "").strip()
    if not host and (user.endswith("@gmail.com") or user.endswith("@googlemail.com")):
        host = "smtp.gmail.com"

    driver = (get_env("MAIL_DRIVER", required=False) or ("smtp" if (host or user) else "console")).strip().lower()
    if driver == "console":
        return ConsoleTransport()
    if driver != "smtp":
        raise MailError(f"Unknown MAIL_DRIVER {driver!r} (use smtp or console)")
    if not host:
        raise MailError("MAIL_DRIVER=smtp needs SMTP_HOST (e.g. smtp.gmail.com)")
    port = int(get_env("SMTP_PORT", required=False, default="587") or "587")
    secure = (get_env("SMTP_SECURE", required=False) or ("ssl" if port == 465 else "starttls")).strip().lower()
    if secure not in ("ssl", "starttls", "none"):
        raise MailError("SMTP_SECURE must be ssl, starttls or none")
    sender = (get_env("MAIL_FROM", required=False) or user or "").strip()
    if not sender:
        raise MailError("Set MAIL_FROM (or SMTP_USER/SMTP_USERNAME) to the address the email should come from")
    return SmtpTransport(host, port, secure, user or None, password or None, sender, sender_name)


def send(msg: Message) -> None:
    create_transport().send(msg)


# --------------------------------------------------------------------------- #
# Templates
# --------------------------------------------------------------------------- #
_COPY = {
    "reset": ("Your password reset code", "Reset your password",
              "Use this code to choose a new password for your account."),
    "set_password": ("Your code to set a password", "Set a password",
                     "Use this code to add a password to your account, so you can sign in without Google."),
    "verify_email": ("Confirm your new email address", "Confirm your email",
                     "Use this code to confirm this address for your account."),
}


def otp_email(to: str, code: str, purpose: str, name: str = "", minutes: int = 10) -> Message:
    subject, headline, lead = _COPY[purpose]
    try:
        brand = load_brand()
    except Exception:  # noqa: BLE001 -- never fail an email over a missing brand file
        brand = {}
    handle = html.escape(str(brand.get("handle", "")))
    colors = brand.get("colors", {}) or {}
    ink, accent = colors.get("bg", "#0D1117"), colors.get("accent", "#FFB800")
    hello = f"Hi {name.split()[0]}," if name.strip() else "Hi,"
    spaced = " ".join(code)

    text = (f"{hello}\n\n{lead}\n\n    {spaced}\n\nThis code expires in {minutes} minutes and works once. "
            "If you didn't ask for it, you can ignore this email: your password has not changed.\n"
            f"\n{brand.get('handle', '')}\n")
    body = f"""<!doctype html>
<html><body style="margin:0;background:#f3f1ec;padding:32px 12px;font-family:Helvetica,Arial,sans-serif;color:#1b1f24">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
    <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;background:#ffffff;border:1px solid #e3dfd6">
      <tr><td style="background:{ink};padding:22px 28px;border-bottom:4px solid {accent}">
        <span style="color:#ffffff;font-size:13px;letter-spacing:.14em;text-transform:uppercase">{handle or 'Content admin'}</span></td></tr>
      <tr><td style="padding:32px 28px 8px">
        <h1 style="margin:0 0 12px;font-size:22px;line-height:1.25">{html.escape(headline)}</h1>
        <p style="margin:0 0 4px;font-size:15px;line-height:1.55;color:#4a5058">{html.escape(hello)}</p>
        <p style="margin:0;font-size:15px;line-height:1.55;color:#4a5058">{html.escape(lead)}</p></td></tr>
      <tr><td align="center" style="padding:20px 28px 8px">
        <div style="display:inline-block;padding:16px 26px;background:#faf8f3;border:1px dashed #cfc9bb;font-family:'Courier New',monospace;font-size:34px;letter-spacing:.32em;font-weight:700;color:{ink}">{html.escape(code)}</div></td></tr>
      <tr><td style="padding:12px 28px 30px">
        <p style="margin:0;font-size:13px;line-height:1.6;color:#6b717a">Expires in {minutes} minutes and works once. If you didn't ask for this, ignore it: nothing has changed on your account.</p></td></tr>
    </table>
  </td></tr></table>
</body></html>"""
    return Message(to=to, subject=subject, text=text, html=body)
