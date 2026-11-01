"""Signing in, signing out, and the people on a team.

Everything runs through the Next proxy, so these cookies belong to the app's own
origin and the browser never talks to this process directly.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import Field
from sqlalchemy.exc import IntegrityError

from ..auth import accounts, google, mailer
from ..auth.accounts import AuthContext, MEMBER, OWNER, SESSION_COOKIE
from ..config import Settings, get_settings
from ..schemas.common import SalixModel
from ..store import repo
from ..store.models import InviteRow, OrgRow, UserRow, utcnow
from .deps import OrgId, Session, require_session

log = logging.getLogger("salix.routers.auth")

router = APIRouter(prefix="/auth", tags=["auth"])
team_router = APIRouter(prefix="/team", tags=["team"])

ATTEMPT_COOKIE = "salix_oauth"
ATTEMPT_MAX_AGE = 600
EMAIL = re.compile(r"^[^@\s]{1,120}@[^@\s]{1,200}\.[^@\s]{2,}$")


class UserOut(SalixModel):
    id: str
    email: str
    name: str
    picture: str = ""
    role: str
    rep_id: Optional[str] = None
    org_id: str
    org_name: str = ""


class Me(SalixModel):
    auth_required: bool
    google_enabled: bool
    user: Optional[UserOut] = None


class InviteRequest(SalixModel):
    email: str = Field(max_length=320)
    rep_id: Optional[str] = None


class InviteOut(SalixModel):
    id: str
    email: str
    role: str
    rep_id: Optional[str] = None
    #: Whether the mail server took it, for this request. Not a delivery receipt.
    email_sent: bool = False


class TeamOut(SalixModel):
    members: list[UserOut] = Field(default_factory=list)
    invites: list[InviteOut] = Field(default_factory=list)
    can_manage: bool = False
    mail_enabled: bool = False


class RoleChange(SalixModel):
    role: str


class OrgRename(SalixModel):
    name: str = Field(min_length=1, max_length=120)


def _set_cookie(response: Response, settings: Settings, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path="/",
        httponly=True,
        # Sent on the top-level redirect back from Google, and not on a form
        # posted from another site, which is the protection against CSRF here.
        samesite="lax",
        secure=settings.app_url.lower().startswith("https://"),
    )


def _failed(settings: Settings, reason: str) -> RedirectResponse:
    response = RedirectResponse(
        f"{settings.app_url.rstrip('/')}/login?error={reason}", status_code=302
    )
    response.delete_cookie(ATTEMPT_COOKIE, path="/")
    return response


async def _user_out(session, user: UserRow) -> UserOut:
    org = await session.get(OrgRow, user.org_id)
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        picture=user.picture or "",
        role=user.role,
        rep_id=user.rep_id,
        org_id=user.org_id,
        org_name=org.name if org else "",
    )


@router.get("/me", response_model=Me)
async def me(request: Request, session: Session) -> Me:
    """Public: the page has to ask this before it knows whether to show a login."""
    settings = get_settings()
    out = Me(auth_required=settings.auth_required, google_enabled=settings.google_configured)
    if settings.auth_required:
        context = await accounts.resolve_session(session, request.cookies.get(SESSION_COOKIE))
        if context is not None:
            user = await session.get(UserRow, context.user_id)
            out.user = await _user_out(session, user)
    return out


@router.get("/google/start")
async def google_start(next: str = "/console") -> RedirectResponse:
    settings = get_settings()
    if not settings.google_configured:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured on this server.")

    attempt = google.new_attempt()
    response = RedirectResponse(google.authorization_url(settings, attempt), status_code=302)
    _set_cookie(
        response,
        settings,
        ATTEMPT_COOKIE,
        json.dumps(
            {
                "state": attempt.state,
                "nonce": attempt.nonce,
                "verifier": attempt.verifier,
                "next": google.safe_next(next),
            },
            separators=(",", ":"),
        ).replace('"', "'").replace(",", "|"),
        ATTEMPT_MAX_AGE,
    )
    return response


def _read_attempt(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        data = json.loads(raw.replace("|", ",").replace("'", '"'))
    except ValueError:
        return None
    if not isinstance(data, dict) or not all(
        isinstance(data.get(k), str) for k in ("state", "nonce", "verifier", "next")
    ):
        return None
    return data


@router.get("/google/callback")
async def google_callback(
    request: Request,
    session: Session,
    code: str = "",
    state: str = "",
    error: str = "",
) -> RedirectResponse:
    settings = get_settings()
    if not settings.google_configured:
        return _failed(settings, "not_configured")
    if error:
        # The person pressed cancel, most of the time.
        return _failed(settings, "cancelled")

    import secrets

    attempt = _read_attempt(request.cookies.get(ATTEMPT_COOKIE))
    if attempt is None or not state or not secrets.compare_digest(attempt["state"], state):
        log.warning("google callback with a missing or mismatched state")
        return _failed(settings, "expired")
    if not code:
        return _failed(settings, "cancelled")

    try:
        token = await google.exchange_code(settings, code, attempt["verifier"])
        profile = await google.verify_id_token(settings, token, attempt["nonce"])
    except google.GoogleError as exc:
        log.warning("google sign-in failed: %s", exc)
        return _failed(settings, "failed")

    user = await accounts.sign_in(session, profile, settings)
    session_token = await accounts.create_session(session, user.id, settings)
    await session.commit()

    response = RedirectResponse(
        f"{settings.app_url.rstrip('/')}{google.safe_next(attempt['next'])}", status_code=302
    )
    _set_cookie(
        response, settings, SESSION_COOKIE, session_token, settings.session_days * 86400
    )
    response.delete_cookie(ATTEMPT_COOKIE, path="/")
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request, session: Session) -> Response:
    await accounts.end_session(session, request.cookies.get(SESSION_COOKIE))
    await session.commit()
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# --------------------------------------------------------------------------
# The team
# --------------------------------------------------------------------------


def _context(request: Request) -> Optional[AuthContext]:
    return getattr(request.state, "auth", None)


def _require_owner(request: Request) -> AuthContext:
    context = _context(request)
    if context is None:
        raise HTTPException(status_code=404, detail="Accounts are not enabled on this deployment.")
    if context.role != OWNER:
        raise HTTPException(status_code=403, detail="Only the team owner can do that.")
    return context


@team_router.get("", response_model=TeamOut, dependencies=[Depends(require_session)])
async def team(request: Request, session: Session) -> TeamOut:
    context = _context(request)
    if context is None:
        return TeamOut(mail_enabled=get_settings().mail_configured)
    return TeamOut(
        members=[await _user_out(session, u) for u in await accounts.members(session, context.org_id)],
        invites=[
            InviteOut(id=i.id, email=i.email, role=i.role, rep_id=i.rep_id)
            for i in await accounts.invites(session, context.org_id)
        ],
        can_manage=context.role == OWNER,
        mail_enabled=get_settings().mail_configured,
    )


@team_router.post("/invites", response_model=InviteOut, status_code=201, dependencies=[Depends(require_session)])
async def invite(request: Request, session: Session, org_id: OrgId, body: InviteRequest) -> InviteOut:
    """They join this team the first time they sign in with this address, and are
    told by email if a mail server is configured."""
    context = _require_owner(request)
    email = body.email.strip().lower()
    if not EMAIL.fullmatch(email):
        raise HTTPException(status_code=422, detail="That does not look like an email address.")

    if any(u.email == email for u in await accounts.members(session, org_id)):
        raise HTTPException(status_code=409, detail=f"{email} is already on this team.")

    if body.rep_id:
        rep = await repo.get_rep(session, body.rep_id)
        if rep is None or rep.org_id != org_id:
            raise HTTPException(status_code=400, detail=f"No rep {body.rep_id}")

    row = InviteRow(
        id=f"inv_{uuid.uuid4().hex[:12]}",
        org_id=org_id,
        email=email,
        role=MEMBER,
        rep_id=body.rep_id,
        created_at=utcnow(),
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail=f"{email} has already been invited.")
    return InviteOut(
        id=row.id,
        email=row.email,
        role=row.role,
        rep_id=row.rep_id,
        email_sent=await _send_invite(session, context, row.email),
    )


async def _send_invite(session, context: AuthContext, email: str) -> bool:
    inviter = await session.get(UserRow, context.user_id)
    org = await session.get(OrgRow, context.org_id)
    return await mailer.send_invite(
        get_settings(),
        to=email,
        team=org.name if org else "their team",
        inviter=inviter.name if inviter else "A colleague",
    )


@team_router.post("/invites/{invite_id}/resend", response_model=InviteOut, dependencies=[Depends(require_session)])
async def resend_invite(request: Request, session: Session, invite_id: str) -> InviteOut:
    context = _require_owner(request)
    row = await session.get(InviteRow, invite_id)
    if row is None or row.org_id != context.org_id:
        raise HTTPException(status_code=404, detail=f"No invite {invite_id}")
    return InviteOut(
        id=row.id,
        email=row.email,
        role=row.role,
        rep_id=row.rep_id,
        email_sent=await _send_invite(session, context, row.email),
    )


@team_router.patch("/members/{user_id}", response_model=UserOut, dependencies=[Depends(require_session)])
async def change_role(request: Request, session: Session, user_id: str, body: RoleChange) -> UserOut:
    context = _require_owner(request)
    if body.role not in (OWNER, MEMBER):
        raise HTTPException(status_code=422, detail="A role is either owner or member.")
    user = await session.get(UserRow, user_id)
    if user is None or user.org_id != context.org_id:
        raise HTTPException(status_code=404, detail=f"No member {user_id}")
    if body.role == MEMBER and user.role == OWNER:
        owners = [m for m in await accounts.members(session, context.org_id) if m.role == OWNER]
        if len(owners) <= 1:
            raise HTTPException(status_code=409, detail="A team needs at least one owner.")
    user.role = body.role
    await session.commit()
    return await _user_out(session, user)


@team_router.delete("/invites/{invite_id}", status_code=204, dependencies=[Depends(require_session)])
async def cancel_invite(request: Request, session: Session, invite_id: str) -> None:
    context = _require_owner(request)
    row = await session.get(InviteRow, invite_id)
    if row is None or row.org_id != context.org_id:
        raise HTTPException(status_code=404, detail=f"No invite {invite_id}")
    await session.delete(row)
    await session.commit()


@team_router.delete("/members/{user_id}", status_code=204, dependencies=[Depends(require_session)])
async def remove_member(request: Request, session: Session, user_id: str) -> None:
    context = _require_owner(request)
    user = await session.get(UserRow, user_id)
    if user is None or user.org_id != context.org_id:
        raise HTTPException(status_code=404, detail=f"No member {user_id}")
    if user.id == context.user_id:
        raise HTTPException(status_code=409, detail="You cannot remove yourself from your own team.")
    await accounts.remove_member(session, user)
    await session.commit()


@team_router.patch("/org", dependencies=[Depends(require_session)])
async def rename_org(request: Request, session: Session, body: OrgRename) -> dict:
    context = _require_owner(request)
    org = await repo.get_org(session, context.org_id)
    org.name = body.name.strip() or org.name
    await repo.put_org(session, org)
    await session.commit()
    return {"name": org.name}
