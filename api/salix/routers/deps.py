"""Shared router dependencies.

With accounts on, the signed-in person's session decides the organisation for
the whole request. With them off, there is one organisation and it is resolved
once and cached, so a fresh clone runs with no setup.

`require_session` is attached to every data router in `app.py`, rather than to each
route, so a new endpoint is protected by default. `owned` is what an endpoint uses
when it looks something up by id: being signed in does not make a record yours.
"""

from __future__ import annotations

from typing import Annotated, Optional, TypeVar

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import accounts
from ..config import get_settings
from ..providers.base import Providers
from ..store import repo
from ..store.db import get_session, session_scope

Session = Annotated[AsyncSession, Depends(get_session)]

_cached_org_id: str | None = None


#: The exact words the browser looks for to tell "go and sign in" apart from a
#: mismatched API key, which is also a 401 and means something else entirely.
SIGN_IN_REQUIRED = "Sign in to continue."

T = TypeVar("T")


async def require_session(request: Request) -> None:
    """Refuse anyone not signed in, when accounts are on.

    Its own short transaction, not the request's: this guards streams that stay
    open for minutes, and must not hold a database connection for all of it.
    """
    if not get_settings().auth_required:
        return
    async with session_scope() as session:
        context = await accounts.resolve_session(
            session, request.cookies.get(accounts.SESSION_COOKIE)
        )
    if context is None:
        raise HTTPException(status_code=401, detail=SIGN_IN_REQUIRED)
    request.state.auth = context


async def require_owner(request: Request, _: None = Depends(require_session)) -> None:
    """For changes to who is on the team and for spending the team's money. With
    accounts off there is nobody to tell apart, so nothing is restricted."""
    if is_restricted_member(request):
        raise HTTPException(status_code=403, detail="Only the team owner can do that.")


def is_restricted_member(request: Request) -> bool:
    context = getattr(request.state, "auth", None)
    return context is not None and context.role != accounts.OWNER


def owned(item: Optional[T], org_id: str, label: str, item_id: str) -> T:
    """The record, if it is this organisation's.

    The same 404 for "not yours" and "not there", so ids cannot be probed.
    """
    if item is None or getattr(item, "org_id", None) != org_id:
        raise HTTPException(status_code=404, detail=f"No {label} {item_id}")
    return item


async def current_org_id(
    request: Request, session: Session, _: None = Depends(require_session)
) -> str:
    context = getattr(request.state, "auth", None)
    if context is not None:
        return context.org_id

    global _cached_org_id
    if _cached_org_id is None:
        org = await repo.first_org(session)
        if org is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "No organisation in the database. Run `python -m seed.build "
                    "--reset` from the repository root to populate it."
                ),
            )
        _cached_org_id = org.id
    return _cached_org_id


def reset_org_cache() -> None:
    global _cached_org_id
    _cached_org_id = None


def get_providers_dep(request: Request) -> Providers:
    return request.app.state.providers


OrgId = Annotated[str, Depends(current_org_id)]
Prov = Annotated[Providers, Depends(get_providers_dep)]
