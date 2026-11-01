"""Sending the one email this product sends: an invitation.

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
        f"Sign in with Google using this address ({to}) and you will join the team:\n"
        f"{link}\n"
    )
    try:
        await asyncio.to_thread(_send, settings, message)
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("could not send an invitation: %s", type(exc).__name__)
        return False
    return True
