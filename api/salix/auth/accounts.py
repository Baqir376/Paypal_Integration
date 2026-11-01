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
from ..store.models import InviteRow, SessionRow, UserRow, utcnow
from .google import GoogleProfile

log = logging.getLogger("salix.auth")

SESSION_COOKIE = "salix_session"
OWNER = "owner"
MEMBER = "member"


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


async def _org_for_new_user(
    session: AsyncSession, profile: GoogleProfile, settings: Settings
) -> tuple[str, str, Optional[str]]:
    """(org id, role, rep id) for somebody signing in for the first time."""
    invite = (
        await session.execute(
            select(InviteRow)
            .where(InviteRow.email == profile.email)
            .order_by(InviteRow.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if invite is not None:
        org_id, role, rep_id = invite.org_id, invite.role, invite.rep_id
        await session.delete(invite)
        return org_id, role, rep_id

    # The person running this deployment claims the data already in it. Named
    # outright, because "first person to sign in" hands a live database to
    # whichever stranger finds the login page first.
    if settings.owner_email and profile.email == settings.owner_email.strip().lower():
        org = await repo.first_org(session)
        if org is not None:
            taken = (
                await session.execute(
                    select(func.count()).select_from(UserRow).where(UserRow.org_id == org.id)
                )
            ).scalar_one()
            if not taken:
                return org.id, OWNER, None

    org_id = f"org_{uuid.uuid4().hex[:12]}"
    first_name = profile.name.split()[0] if profile.name.split() else "My"
    await repo.put_org(session, Org(id=org_id, name=f"{first_name}'s team"))
    return org_id, OWNER, None


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
    await session.delete(user)
