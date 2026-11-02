"""Sending the emails this product sends: an invitation, and account links.

Plain SMTP, so any provider works and none is written into the code. A failure is
reported rather than raised: the invitation exists either way, and whoever sent it
can tell the colleague themselves.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from ..config import Settings

log = logging.getLogger("salix.auth.mailer")

TIMEOUT_S = 15


def _one_line(text: str) -> str:
    """A team name comes from a person and goes into a header."""
    return " ".join(text.split())[:120]


def _send(settings: Settings, message: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=TIMEOUT_S) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password or "")
        smtp.send_message(message)


async def _deliver(settings: Settings, *, to: str, subject: str, body: str) -> bool:
    if not settings.mail_configured:
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = to
    message.set_content(body)
    try:
        await asyncio.to_thread(_send, settings, message)
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("could not send an account email: %s", type(exc).__name__)
        return False
    return True


async def send_verification(settings: Settings, *, to: str, token: str) -> bool:
    link = f"{settings.app_url.rstrip('/')}/api/auth/email/verify?token={token}"
    return await _deliver(
        settings,
        to=to,
        subject="Confirm your email for Salix",
        body=(
            f"Confirm this address to finish setting up your Salix account:\n{link}\n\n"
            "If you did not sign up, ignore this email and do not open the link.\n"
        ),
    )


async def send_password_reset(settings: Settings, *, to: str, token: str) -> bool:
    link = f"{settings.app_url.rstrip('/')}/reset-password?token={token}"
    return await _deliver(
        settings,
        to=to,
        subject="Reset your Salix password",
        body=(
            f"Choose a new password here. The link works for one hour:\n{link}\n\n"
            "If you did not ask for this, ignore this email and your password stays as it is.\n"
        ),
    )


async def send_invite(settings: Settings, *, to: str, team: str, inviter: str) -> bool:
    """True if the mail server accepted it."""
    if not settings.mail_configured:
        return False

    team, inviter = _one_line(team), _one_line(inviter)
    link = f"{settings.app_url.rstrip('/')}/login"
    message = EmailMessage()
    message["Subject"] = f"{inviter} invited you to {team} on Salix"
    message["From"] = settings.smtp_from
    message["To"] = to
    message.set_content(
        f"{inviter} has invited you to join {team} on Salix.\n\n"
        f"Sign in using this address ({to}), with Google or a password, and you will "
        "join the team:\n"
        f"{link}\n"
    )
    try:
        await asyncio.to_thread(_send, settings, message)
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("could not send an invitation: %s", type(exc).__name__)
        return False
    return True
