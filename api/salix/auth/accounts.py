"""People, their sessions, and which team they are on.

A session token is random and only its hash is stored, so reading the database
does not let anybody sign in as anyone. Everything a person can see hangs off
`users.org_id`: resolving the session is what decides the organisation for the
whole request.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..schemas.org import Org
from ..store import repo
from ..store.models import (
    CallRow,
    CreditAccountRow,
    EmailTokenRow,
    InviteRow,
    PasswordRow,
    SessionRow,
    UserRow,
    utcnow,
)
from . import passwords
from .google import GoogleProfile

log = logging.getLogger("salix.auth")

SESSION_COOKIE = "salix_session"
OWNER = "owner"
MEMBER = "member"

#: What `users.google_sub` holds until a password account first signs in with Google.
PASSWORD_SUB = "password:"
VERIFY = "verify"
RESET = "reset"
TOKEN_LIFETIME = {VERIFY: timedelta(days=3), RESET: timedelta(hours=1)}
MAX_FAILURES = 10
LOCKED_FOR = timedelta(minutes=15)


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    org_id: str
    role: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _naive(moment):
    """SQLite gives back naive datetimes and Postgres aware ones."""
    return moment.replace(tzinfo=None) if moment.tzinfo else moment


async def create_session(session: AsyncSession, user_id: str, settings: Settings) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        SessionRow(
            token_hash=_hash(token),
            user_id=user_id,
            created_at=utcnow(),
            expires_at=utcnow() + timedelta(days=settings.session_days),
        )
    )
    return token


async def resolve_session(session: AsyncSession, token: Optional[str]) -> Optional[AuthContext]:
    if not token:
        return None
    row = await session.get(SessionRow, _hash(token))
    if row is None:
        return None
    if _naive(row.expires_at) <= _naive(utcnow()):
        await session.delete(row)
        return None
    user = await session.get(UserRow, row.user_id)
    if user is None:
        await session.delete(row)
        return None
    return AuthContext(user_id=user.id, org_id=user.org_id, role=user.role)


async def end_session(session: AsyncSession, token: Optional[str]) -> None:
    if token:
        await session.execute(delete(SessionRow).where(SessionRow.token_hash == _hash(token)))


async def _claim(
    session: AsyncSession, email: str, settings: Settings
) -> tuple[Optional[tuple[str, str, Optional[str]]], Optional[InviteRow]]:
    """What a proven address is entitled to: (org id, role, rep id), and the invite behind it."""
    invite = (
        await session.execute(
            select(InviteRow)
            .where(InviteRow.email == email)
            .order_by(InviteRow.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if invite is not None:
        return (invite.org_id, invite.role, invite.rep_id), invite

    # The person running this deployment claims the data already in it. Named
    # outright, because "first person to sign in" hands a live database to
    # whichever stranger finds the login page first.
    if settings.owner_email and email == settings.owner_email.strip().lower():
        org = await repo.first_org(session)
        if org is not None:
            taken = (
                await session.execute(
                    select(func.count()).select_from(UserRow).where(UserRow.org_id == org.id)
                )
            ).scalar_one()
            if not taken:
                return (org.id, OWNER, None), None
    return None, None


async def _new_team(session: AsyncSession, name: str) -> str:
    org_id = f"org_{uuid.uuid4().hex[:12]}"
    first_name = name.split()[0] if name.split() else "My"
    await repo.put_org(session, Org(id=org_id, name=f"{first_name}'s team"))
    return org_id


async def _org_for_new_user(
    session: AsyncSession, profile: GoogleProfile, settings: Settings
) -> tuple[str, str, Optional[str]]:
    """(org id, role, rep id) for somebody signing in for the first time."""
    claim, invite = await _claim(session, profile.email, settings)
    if claim is not None:
        if invite is not None:
            await session.delete(invite)
        return claim
    return await _new_team(session, profile.name), OWNER, None


async def sign_in(session: AsyncSession, profile: GoogleProfile, settings: Settings) -> UserRow:
    """Find or create the account behind a verified Google identity.

    Keyed on Google's `sub`, which never changes, and not on email, which can.
    """
    user = (
        await session.execute(select(UserRow).where(UserRow.google_sub == profile.sub))
    ).scalar_one_or_none()
    if user is not None:
        user.email, user.name, user.picture = profile.email, profile.name, profile.picture
        user.last_login_at = utcnow()
        return user

    user = await _link_password_account(session, profile, settings)
    if user is not None:
        return user

    org_id, role, rep_id = await _org_for_new_user(session, profile, settings)
    user = UserRow(
        id=f"usr_{uuid.uuid4().hex[:12]}",
        google_sub=profile.sub,
        email=profile.email,
        name=profile.name,
        picture=profile.picture,
        org_id=org_id,
        role=role,
        rep_id=rep_id,
        created_at=utcnow(),
        last_login_at=utcnow(),
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        # A double-clicked sign-in racing itself. The other one won, and its
        # transaction also took the invite or made the organisation.
        await session.rollback()
        return (
            await session.execute(select(UserRow).where(UserRow.google_sub == profile.sub))
        ).scalar_one()
    log.info("new account %s joined %s as %s", user.id, org_id, role)
    return user


async def _link_password_account(
    session: AsyncSession, profile: GoogleProfile, settings: Settings
) -> Optional[UserRow]:
    """Google has proved this address, and a password account already claims it.

    If that account never proved the address, whoever made it might not be the person
    now arriving, so their password and sessions end here and the account is the Google
    owner's. An unproven account cannot have invited anybody, so nobody else is left in.
    """
    row = (
        await session.execute(select(PasswordRow).where(PasswordRow.email == profile.email))
    ).scalar_one_or_none()
    if row is None:
        return None
    user = await session.get(UserRow, row.user_id)
    if user is None or not user.google_sub.startswith(PASSWORD_SUB):
        return None

    unproven = not row.verified
    if unproven:
        await session.delete(row)
        await end_all_sessions(session, user.id)
        await session.execute(delete(EmailTokenRow).where(EmailTokenRow.user_id == user.id))
    user.google_sub = profile.sub
    user.email, user.name, user.picture = profile.email, profile.name, profile.picture
    user.last_login_at = utcnow()
    if unproven:
        await _take_up_claim(session, user, settings)
    return user


async def end_all_sessions(session: AsyncSession, user_id: str) -> None:
    await session.execute(delete(SessionRow).where(SessionRow.user_id == user_id))


async def _take_up_claim(session: AsyncSession, user: UserRow, settings: Settings) -> None:
    """Now the address is proven, move them to the team it was invited to.

    Only out of a team with nothing in it. Otherwise the calls and credits would be left
    behind where nobody could reach them, so the invitation waits and they stay put.
    """
    claim, invite = await _claim(session, user.email, settings)
    if claim is None or claim[0] == user.org_id:
        return
    if len(await members(session, user.org_id)) > 1:
        return
    calls = (
        await session.execute(
            select(func.count()).select_from(CallRow).where(CallRow.org_id == user.org_id)
        )
    ).scalar_one()
    credits = (
        await session.execute(
            select(CreditAccountRow.balance).where(CreditAccountRow.org_id == user.org_id)
        )
    ).scalar_one_or_none()
    if calls or credits:
        return
    user.org_id, user.role, user.rep_id = claim
    if invite is not None:
        await session.delete(invite)


class EmailTaken(Exception):
    pass


async def sign_up(session: AsyncSession, *, email: str, name: str, password: str) -> UserRow:
    """A new account with a private team. Its address is unproven, so it claims nothing."""
    taken = (
        await session.execute(select(PasswordRow.user_id).where(PasswordRow.email == email))
    ).first() or (await session.execute(select(UserRow.id).where(UserRow.email == email))).first()
    if taken:
        raise EmailTaken

    hashed = await passwords.hash_password(password)
    user = UserRow(
        id=f"usr_{uuid.uuid4().hex[:12]}",
        google_sub=f"{PASSWORD_SUB}{uuid.uuid4().hex}",
        email=email,
        name=name,
        picture="",
        org_id=await _new_team(session, name),
        role=OWNER,
        rep_id=None,
        created_at=utcnow(),
        last_login_at=utcnow(),
    )
    session.add(user)
    session.add(PasswordRow(user_id=user.id, email=email, hash=hashed, created_at=utcnow()))
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise EmailTaken from None
    log.info("new password account %s", user.id)
    return user


async def log_in(session: AsyncSession, email: str, password: str) -> Optional[UserRow]:
    """The account, or None. The caller commits either way, to keep the count of failures."""
    row = (
        await session.execute(select(PasswordRow).where(PasswordRow.email == email))
    ).scalar_one_or_none()
    if row is None:
        await passwords.waste_a_check(password)
        return None
    if row.locked_until is not None and _naive(row.locked_until) > _naive(utcnow()):
        await passwords.waste_a_check(password)
        return None
    if not await passwords.check_password(password, row.hash):
        row.failed_attempts += 1
        if row.failed_attempts >= MAX_FAILURES:
            row.failed_attempts = 0
            row.locked_until = utcnow() + LOCKED_FOR
        return None
    user = await session.get(UserRow, row.user_id)
    if user is None:
        return None
    row.failed_attempts, row.locked_until = 0, None
    user.last_login_at = utcnow()
    return user


async def email_verified(session: AsyncSession, user_id: str) -> bool:
    """Google proves the address itself, so only a password can leave it unproven."""
    row = await session.get(PasswordRow, user_id)
    return row is None or row.verified


async def user_for_email(session: AsyncSession, email: str) -> Optional[UserRow]:
    row = (
        await session.execute(select(PasswordRow).where(PasswordRow.email == email))
    ).scalar_one_or_none()
    if row is not None:
        return await session.get(UserRow, row.user_id)
    return (
        await session.execute(select(UserRow).where(UserRow.email == email).limit(1))
    ).scalars().first()


async def issue_token(session: AsyncSession, user_id: str, purpose: str) -> str:
    """A new link replaces the last one of its kind."""
    await session.execute(
        delete(EmailTokenRow).where(EmailTokenRow.user_id == user_id, EmailTokenRow.purpose == purpose)
    )
    token = secrets.token_urlsafe(32)
    session.add(
        EmailTokenRow(
            token_hash=_hash(token),
            user_id=user_id,
            purpose=purpose,
            expires_at=utcnow() + TOKEN_LIFETIME[purpose],
        )
    )
    return token


async def user_for_token(session: AsyncSession, token: str, purpose: str) -> Optional[UserRow]:
    row = await session.get(EmailTokenRow, _hash(token))
    if row is None or row.purpose != purpose:
        return None
    if _naive(row.expires_at) <= _naive(utcnow()):
        await session.delete(row)
        return None
    return await session.get(UserRow, row.user_id)


async def confirm_email(session: AsyncSession, user: UserRow, settings: Settings) -> None:
    row = await session.get(PasswordRow, user.id)
    if row is None or row.verified:
        return
    row.verified = True
    await _take_up_claim(session, user, settings)


async def reset_password(session: AsyncSession, user: UserRow, password: str, settings: Settings) -> None:
    """Whoever opened the mail owns the address. Every other browser is signed out, in
    case that is why the password is being changed. A Google account can gain a password
    this way too."""
    hashed = await passwords.hash_password(password)
    row = await session.get(PasswordRow, user.id)
    if row is None:
        session.add(PasswordRow(user_id=user.id, email=user.email, hash=hashed, verified=True, created_at=utcnow()))
    else:
        row.hash, row.failed_attempts, row.locked_until = hashed, 0, None
        await confirm_email(session, user, settings)
    await end_all_sessions(session, user.id)
    await session.execute(
        delete(EmailTokenRow).where(EmailTokenRow.user_id == user.id, EmailTokenRow.purpose == RESET)
    )


async def members(session: AsyncSession, org_id: str) -> list[UserRow]:
    rows = await session.execute(
        select(UserRow).where(UserRow.org_id == org_id).order_by(UserRow.created_at)
    )
    return list(rows.scalars())


async def invites(session: AsyncSession, org_id: str) -> list[InviteRow]:
    rows = await session.execute(
        select(InviteRow).where(InviteRow.org_id == org_id).order_by(InviteRow.created_at)
    )
    return list(rows.scalars())


async def remove_member(session: AsyncSession, user: UserRow) -> None:
    await session.execute(delete(SessionRow).where(SessionRow.user_id == user.id))
    await session.execute(delete(PasswordRow).where(PasswordRow.user_id == user.id))
    await session.execute(delete(EmailTokenRow).where(EmailTokenRow.user_id == user.id))
    await session.delete(user)
