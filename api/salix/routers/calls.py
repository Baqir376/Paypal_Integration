"""Calls: listing, detail, upload and the live pipeline stream."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from ..billing import credits
from ..config import get_settings
from ..schemas.analysis import CallAnalysis
from ..schemas.call import Call, CallStatus, Transcript
from ..schemas.common import CallOutcome, SalixModel
from ..schemas.metrics import CallMetrics, Scorecard
from ..providers.mock import MockASR
from ..providers.storage import build_storage
from ..pipeline.bus import bus
from ..pipeline.orchestrator import run_in_background
from ..store import repo, session_scope
from .deps import OrgId, Prov, Session, is_restricted_member, owned
from .reps import resolve_salesperson

log = logging.getLogger("salix.routers.calls")

router = APIRouter(prefix="/calls", tags=["calls"])

STREAM_KEEPALIVE_S = 15.0

# Audio formats Model Studio accepts for file transcription.
ALLOWED_SUFFIXES = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
    ".mp4", ".mov", ".webm", ".mkv", ".amr",
}
#: Fallback ceiling. The live one comes from SALIX_MAX_UPLOAD_MB, read per
#: request so an operator can lower it without a code change; this constant is
#: what applies when nothing is configured.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024


#: Used when nobody says. An upload needs a file and a name and nothing else.
UNSPECIFIED_ACCOUNT = "Unspecified account"

NO_CREDITS = "You are out of credits. Each recording uses one; buy more to continue."


def _default_title(typed: str, rep_name: str) -> str:
    """Their words if they called it something, otherwise "Bilal's call"."""
    if re.search(r"\bcall$", typed.strip(), re.IGNORECASE):
        return typed.strip()
    return f"{rep_name.split()[0]}'s call"


def _attach_sample_script(settings, filename: str, call_id: str) -> None:
    """Offline only: a bundled sample keeps its real dialogue.

    The twin cannot listen, so it reads a script beside the audio. The stored file
    is named after the call and not the sample, so the script is put there for it.
    The name is held to a strict pattern before it goes anywhere near a path.
    """
    stem = filename.rsplit(".", 1)[0]
    if not re.fullmatch(r"[\w-]{1,80}", stem):
        return
    script = settings.storage_dir / "samples" / f"{stem}.txt"
    if script.is_file():
        (settings.audio_dir / f"{call_id}.txt").write_bytes(script.read_bytes())


class CallSummary(SalixModel):
    call: dict
    rep_name: str = ""
    score: Optional[float] = None
    talk_ratio_rep: Optional[float] = None
    longest_monologue_ms: Optional[int] = None
    headline: str = ""
    open_objections: int = 0


class CallDetailResponse(SalixModel):
    call: dict
    rep_name: str = ""
    deal: Optional[dict] = None
    transcript: Optional[dict] = None
    metrics: Optional[dict] = None
    scorecard: Optional[dict] = None
    analysis: Optional[dict] = None
    plays: list[dict] = []
    citation_coverage: float = 0.0


@router.get("", response_model=list[CallSummary])
async def list_calls(
    session: Session,
    org_id: OrgId,
    rep_id: str | None = None,
    deal_id: str | None = None,
    # Bounded rather than free. A negative limit is meaningless and a
    # ten-million limit is a way to make the server assemble every call it has
    # into one response; both used to answer 200 and let the database decide.
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CallSummary]:
    calls = await repo.list_calls(
        session, org_id, rep_id=rep_id, deal_id=deal_id, limit=limit
    )
    if not calls:
        return []

    ids = [c.id for c in calls]
    metrics = await repo.get_artifacts_for(session, ids, repo.METRICS)
    scorecards = await repo.get_artifacts_for(session, ids, repo.SCORECARD)
    analyses = await repo.get_artifacts_for(session, ids, repo.ANALYSIS)
    reps = {r.id: r.name for r in await repo.list_reps(session, org_id)}

    summaries: list[CallSummary] = []
    for call in calls:
        m = metrics.get(call.id)
        s = scorecards.get(call.id)
        a = analyses.get(call.id)
        summaries.append(
            CallSummary(
                call=call.model_dump(mode="json"),
                rep_name=reps.get(call.rep_id, ""),
                score=s.get("overall") if s else None,
                talk_ratio_rep=m.get("talk_ratio_rep") if m else None,
                longest_monologue_ms=m.get("longest_monologue_ms") if m else None,
                headline=a.get("headline", "") if a else "",
                open_objections=(
                    sum(1 for o in a.get("objections", []) if not o.get("handled"))
                    if a
                    else 0
                ),
            )
        )
    return summaries


@router.get("/{call_id}", response_model=CallDetailResponse)
async def get_call(session: Session, org_id: OrgId, call_id: str) -> CallDetailResponse:
    call = owned(await repo.get_call(session, call_id), org_id, "call", call_id)

    transcript = await repo.get_artifact(session, call_id, repo.TRANSCRIPT, Transcript)
    metrics = await repo.get_artifact(session, call_id, repo.METRICS, CallMetrics)
    scorecard = await repo.get_artifact(session, call_id, repo.SCORECARD, Scorecard)
    analysis = await repo.get_artifact(session, call_id, repo.ANALYSIS, CallAnalysis)

    rep = await repo.get_rep(session, call.rep_id)
    deal = await repo.get_deal(session, call.deal_id) if call.deal_id else None

    # Plays are stored org-wide; surface only the instances from this call.
    plays: list[dict] = []
    for play in await repo.list_plays(session, org_id):
        instance = next((i for i in play.instances if i.call_id == call_id), None)
        if instance is None:
            continue
        payload = play.model_dump(mode="json")
        payload["instance"] = instance.model_dump(mode="json")
        payload["win_rate_lift"] = play.win_rate_lift
        plays.append(payload)

    coverage = 0.0
    if analysis is not None:
        from ..agents.evidence import citation_coverage

        coverage = citation_coverage(analysis)

    return CallDetailResponse(
        call=call.model_dump(mode="json"),
        rep_name=rep.name if rep else "",
        deal=deal.model_dump(mode="json") if deal else None,
        transcript=transcript.model_dump(mode="json") if transcript else None,
        metrics=metrics.model_dump(mode="json") if metrics else None,
        scorecard=scorecard.model_dump(mode="json") if scorecard else None,
        analysis=analysis.model_dump(mode="json") if analysis else None,
        plays=plays,
        citation_coverage=coverage,
    )


@router.post("/upload", status_code=202)
async def upload_call(
    request: Request,
    session: Session,
    org_id: OrgId,
    providers: Prov,
    background: BackgroundTasks,
    file: UploadFile,
    # All a person has to give: "Bilal" or "Bilal's Call". Someone new is added
    # to the team. `rep_id` is for callers who already know exactly who it is.
    salesperson: str = Form(""),
    rep_id: str = Form(""),
    title: str = Form(""),
    account: str = Form(""),
    deal_id: str = Form(""),
    outcome: str = Form("open"),
    rep_speaker_id: str = Form(""),
    # Detected from the recording. Only for API callers who know better; nothing
    # in the product sends it.
    language: str = Form(""),
) -> dict:
    """Accept a recording and start the analysis DAG.

    Returns 202 immediately with the call id and the SSE URL. The browser
    subscribes to that stream and watches the graph run; nothing about the
    upload blocks on inference.
    """
    settings = get_settings()
    max_bytes = max(1, settings.max_upload_mb) * 1024 * 1024

    # Refuse an oversized file before reading a byte of it. The loop below
    # catches it either way, but only after streaming the whole thing across
    # the wire -- on a sales floor's upstream that is minutes of waiting for a
    # rejection the client could have been given immediately.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes * 1.05:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_upload_mb}MB",
        )

    suffix = ("." + file.filename.rsplit(".", 1)[-1].lower()) if "." in (file.filename or "") else ""
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported audio format '{suffix or file.filename}'. "
                f"Accepted: {', '.join(sorted(ALLOWED_SUFFIXES))}"
            ),
        )

    if deal_id and (
        (deal := await repo.get_deal(session, deal_id)) is None or deal.org_id != org_id
    ):
        raise HTTPException(status_code=400, detail=f"No deal {deal_id}")

    if not rep_id.strip() and not salesperson.strip():
        raise HTTPException(status_code=422, detail="Say whose call this is.")

    # Before a byte is read, for the same reason as the size check above. The
    # charge itself comes later and is what actually decides.
    if settings.billing_enforced and await credits.balance(session, org_id) < credits.CALL_COST:
        raise HTTPException(status_code=402, detail=NO_CREDITS)

    if rep_id.strip():
        rep = await repo.get_rep(session, rep_id)
        if rep is None or rep.archived or rep.org_id != org_id:
            raise HTTPException(status_code=400, detail=f"No rep {rep_id}")
    else:
        rep = await resolve_salesperson(
            session, org_id, salesperson, may_change_team=not is_restricted_member(request)
        )

    call_id = f"call_{uuid.uuid4().hex[:12]}"
    filename = f"{call_id}{suffix}"

    chunks: list[bytes] = []
    written = 0
    while chunk := await file.read(1024 * 1024):
        written += len(chunk)
        if written > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {settings.max_upload_mb}MB",
            )
        chunks.append(chunk)

    if written == 0:
        raise HTTPException(status_code=400, detail="Uploaded file was empty")

    # In this transaction, with the call row: anything failing below takes the
    # charge back with it.
    if settings.billing_enforced:
        try:
            await credits.spend_for_call(session, org_id, call_id)
        except credits.InsufficientCredits:
            raise HTTPException(status_code=402, detail=NO_CREDITS)

    # The storage backend decides whether the transcriber gets a local path
    # (offline mode) or a reachable URL (OSS, or a configured public host).
    storage = build_storage(settings)
    try:
        stored_at, audio_url = storage.put(b"".join(chunks), filename)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Could not store audio: {exc}")

    if settings.is_live and not storage.serves_public_urls:
        log.warning(
            "live mode with local storage: Model Studio cannot fetch %s. "
            "Configure OSS or SALIX_PUBLIC_BASE_URL.",
            stored_at,
        )

    if isinstance(providers.asr, MockASR):
        _attach_sample_script(settings, file.filename or "", call_id)

    call = Call(
        id=call_id,
        org_id=org_id,
        deal_id=deal_id or None,
        rep_id=rep.id,
        title=title.strip() or _default_title(salesperson, rep.name),
        account=account.strip() or UNSPECIFIED_ACCOUNT,
        occurred_at=datetime.now(timezone.utc),
        audio_url=audio_url,
        status=CallStatus.TRANSCRIBING,
        outcome=CallOutcome(outcome) if outcome in CallOutcome._value2member_map_ else CallOutcome.OPEN,
    )
    await repo.put_call(session, call)
    await session.commit()

    background.add_task(
        run_in_background,
        providers,
        call,
        audio_url=audio_url,
        rep_speaker_id=int(rep_speaker_id) if rep_speaker_id.strip().isdigit() else None,
        rep_name=rep.name,
        language=language.strip().lower() if language.strip().lower() in {"en", "ur", "ur-roman", "multi"} else "",
    )

    log.info("accepted upload %s (%.1f MB) for %s", call_id, written / 1e6, rep.name)
    return {
        "call_id": call_id,
        "status": "accepted",
        "bytes": written,
        "rep_id": rep.id,
        "events_url": f"/api/calls/{call_id}/events",
    }


async def _ensure_owned(request: Request, call_id: str) -> None:
    """For the streams below, which outlive any request-scoped database session."""
    if not get_settings().auth_required:
        return
    async with session_scope() as session:
        call = await repo.get_call(session, call_id)
    owned(call, request.state.auth.org_id, "call", call_id)


async def _pipeline_frames(call_id: str):
    """The SSE frames for one run, with a heartbeat while a stage is quiet.

    The wait must not cancel the pending read: cancelling it ends the
    subscription's generator, so the first quiet stretch would close the stream
    and the browser would announce a finish while the analysis was still going.
    """
    subscription = bus.subscribe(call_id)
    pending: asyncio.Future | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(subscription.__anext__())
            finished, _ = await asyncio.wait({pending}, timeout=STREAM_KEEPALIVE_S)
            if not finished:
                yield ": keepalive\n\n"
                continue
            read, pending = pending, None
            try:
                event = read.result()
            except StopAsyncIteration:
                break
            yield f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"
    except asyncio.CancelledError:  # client navigated away
        raise
    finally:
        if pending is not None:
            pending.cancel()
        yield "event: close\ndata: {}\n\n"


@router.get("/{call_id}/events")
async def stream_events(request: Request, call_id: str) -> StreamingResponse:
    """Server-sent events for one call's pipeline run.

    A heartbeat comment goes out every fifteen seconds so that proxies and
    browsers do not quietly close a stream during a long transcription.
    """
    await _ensure_owned(request, call_id)

    return StreamingResponse(
        _pipeline_frames(call_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{call_id}/timeline")
async def stage_history(request: Request, call_id: str) -> list[dict]:
    """Whatever the pipeline has already reported, for a page reload."""
    await _ensure_owned(request, call_id)
    return [e.model_dump(mode="json") for e in bus.history(call_id)]
