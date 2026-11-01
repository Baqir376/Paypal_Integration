"""Recordings: the most confidential thing in the system.

A route rather than a static mount, because a mount cannot ask who is asking. With
accounts on, a recording is served only to the team that owns the call. The other
way in is a signed, expiring URL, for a transcription service that fetches the file
from its own servers and has no session to present.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ..auth import accounts
from ..config import get_settings
from ..signing import verify
from ..store import repo, session_scope

router = APIRouter(tags=["audio"])

#: A stored file is always `<call id>.<extension>`, written by this server.
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,120}\.[A-Za-z0-9]{1,8}$")


async def _may_read(request: Request, name: str) -> bool:
    settings = get_settings()
    if not settings.auth_required:
        return True
    if settings.api_key and verify(
        settings.api_key, name, request.query_params.get("expires"), request.query_params.get("sig")
    ):
        return True

    async with session_scope() as session:
        context = await accounts.resolve_session(
            session, request.cookies.get(accounts.SESSION_COOKIE)
        )
        if context is None:
            return False
        call = await repo.get_call(session, name.rsplit(".", 1)[0])
        return call is not None and call.org_id == context.org_id


@router.api_route("/audio/{name}", methods=["GET", "HEAD"])
async def recording(request: Request, name: str) -> FileResponse:
    # The same answer for "not yours" and "not there", so this cannot be used to
    # find out which call ids exist.
    missing = HTTPException(status_code=404, detail="No such recording.")
    if not _NAME.fullmatch(name) or not await _may_read(request, name):
        raise missing

    audio_dir = get_settings().audio_dir.resolve()
    path = (audio_dir / name).resolve()
    if path.parent != audio_dir or not path.is_file():
        raise missing
    return FileResponse(path)
