"""Shared router dependencies.

Salix is single-tenant in this build, so rather than thread an org id through
every request the API resolves "the" org once and caches it. `current_org_id`
is the seam: adding real multi-tenancy means changing this function and the
auth layer above it, not every endpoint.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..providers.base import Providers
from ..store import repo
from ..store.db import get_session

Session = Annotated[AsyncSession, Depends(get_session)]

_cached_org_id: str | None = None


async def current_org_id(session: Session) -> str:
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
