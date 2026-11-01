"""Typed repository over the storage tables.

Every function here takes and returns Pydantic models, never rows. Callers in
`agents/`, `pipeline/` and `routers/` therefore work exclusively in the domain
language of the contract, and the JSON-document storage decision stays an
implementation detail of this one module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Sequence, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.analysis import CallAnalysis
from ..schemas.call import Call, CallStatus, Transcript
from ..schemas.coaching import CoachingPlan
from ..schemas.deal import Deal
from ..schemas.dojo import DojoSession
from ..schemas.metrics import CallMetrics, Scorecard
from ..schemas.org import Org, Rep
from ..schemas.play import Play
from ..schemas.report import CycleReport
from . import vectors
from .models import (
    ArtifactRow,
    CallRow,
    CoachingPlanRow,
    DealRow,
    DojoSessionRow,
    MomentRow,
    OrgRow,
    PlayRow,
    RepRow,
    ReportRow,
    utcnow,
)

T = TypeVar("T", bound=BaseModel)

#: The organisation a fresh deployment starts with.
DEFAULT_ORG_ID = "org_default"

# Artifact kinds. Adding an agent output means adding a constant here.
TRANSCRIPT = "transcript"
METRICS = "metrics"
SCORECARD = "scorecard"
ANALYSIS = "analysis"

_ARTIFACT_TYPES: dict[str, type[BaseModel]] = {
    TRANSCRIPT: Transcript,
    METRICS: CallMetrics,
    SCORECARD: Scorecard,
    ANALYSIS: CallAnalysis,
}


def _dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


async def _upsert(session: AsyncSession, row_type, values: dict[str, Any]) -> None:
    """Insert-or-replace keyed on the primary key.

    Uses SQLite's ON CONFLICT for a single round trip; on other backends the
    merge path is used instead.
    """
    if session.bind.dialect.name == "sqlite":
        keys = [c.name for c in row_type.__table__.primary_key.columns]
        statement = sqlite_insert(row_type).values(**values)
        updates = {k: v for k, v in values.items() if k not in keys}
        if updates:
            statement = statement.on_conflict_do_update(
                index_elements=keys, set_=updates
            )
        else:
            statement = statement.on_conflict_do_nothing(index_elements=keys)
        await session.execute(statement)
    else:
        await session.merge(row_type(**values))


# --------------------------------------------------------------------------
# Org and people
# --------------------------------------------------------------------------


async def put_org(session: AsyncSession, org: Org) -> None:
    await _upsert(session, OrgRow, {"id": org.id, "name": org.name, "data": _dump(org)})


async def get_org(session: AsyncSession, org_id: str) -> Optional[Org]:
    row = await session.get(OrgRow, org_id)
    return Org.model_validate(row.data) if row else None


async def first_org(session: AsyncSession) -> Optional[Org]:
    row = (await session.execute(select(OrgRow).limit(1))).scalar_one_or_none()
    return Org.model_validate(row.data) if row else None


async def put_rep(session: AsyncSession, rep: Rep) -> None:
    await _upsert(
        session,
        RepRow,
        {
            "id": rep.id,
            "org_id": rep.org_id,
            "name": rep.name,
            "is_top_performer": int(rep.is_top_performer),
            "data": _dump(rep),
        },
    )


async def get_rep(session: AsyncSession, rep_id: str) -> Optional[Rep]:
    row = await session.get(RepRow, rep_id)
    return Rep.model_validate(row.data) if row else None


async def list_reps(session: AsyncSession, org_id: str) -> list[Rep]:
    rows = (
        await session.execute(
            select(RepRow).where(RepRow.org_id == org_id).order_by(RepRow.name)
        )
    ).scalars()
    return [Rep.model_validate(r.data) for r in rows]


async def top_performers(session: AsyncSession, org_id: str) -> list[Rep]:
    rows = (
        await session.execute(
            select(RepRow).where(
                RepRow.org_id == org_id, RepRow.is_top_performer == 1
            )
        )
    ).scalars()
    reps = [Rep.model_validate(r.data) for r in rows]
    return [r for r in reps if not r.archived]


# --------------------------------------------------------------------------
# Deals
# --------------------------------------------------------------------------


async def put_deal(session: AsyncSession, deal: Deal) -> None:
    await _upsert(
        session,
        DealRow,
        {
            "id": deal.id,
            "org_id": deal.org_id,
            "owner_id": deal.owner_id,
            "stage": deal.stage.value,
            "outcome": deal.outcome.value,
            "value": deal.value,
            "data": _dump(deal),
        },
    )


async def get_deal(session: AsyncSession, deal_id: str) -> Optional[Deal]:
    row = await session.get(DealRow, deal_id)
    return Deal.model_validate(row.data) if row else None


async def list_deals(
    session: AsyncSession, org_id: str, owner_id: Optional[str] = None
) -> list[Deal]:
    query = select(DealRow).where(DealRow.org_id == org_id)
    if owner_id:
        query = query.where(DealRow.owner_id == owner_id)
    rows = (await session.execute(query.order_by(DealRow.value.desc()))).scalars()
    return [Deal.model_validate(r.data) for r in rows]


# --------------------------------------------------------------------------
# Calls
# --------------------------------------------------------------------------


async def put_call(session: AsyncSession, call: Call, score: float = 0.0) -> None:
    await _upsert(
        session,
        CallRow,
        {
            "id": call.id,
            "org_id": call.org_id,
            "deal_id": call.deal_id,
            "rep_id": call.rep_id,
            "occurred_at": call.occurred_at.replace(tzinfo=None),
            "status": call.status.value,
            "outcome": call.outcome.value,
            "duration_ms": call.duration_ms,
            "score": score,
            "data": _dump(call),
        },
    )


async def get_call(session: AsyncSession, call_id: str) -> Optional[Call]:
    row = await session.get(CallRow, call_id)
    return Call.model_validate(row.data) if row else None


async def set_call_status(
    session: AsyncSession,
    call_id: str,
    status: CallStatus,
    error: Optional[str] = None,
) -> None:
    row = await session.get(CallRow, call_id)
    if row is None:
        return
    row.status = status.value
    data = dict(row.data)
    data["status"] = status.value
    if error is not None:
        data["error"] = error
    row.data = data


async def fail_interrupted_calls(session: AsyncSession) -> list[str]:
    """Close out calls that were mid-analysis when the process last stopped.

    The pipeline runs as a background task inside this process. If the process
    goes away while one is running -- a redeploy, an OOM, a power cut -- there
    is nothing left to finish it and nothing that will ever set its status
    again. The call sits in `transcribing` for the rest of time, and the page
    shows a spinner that will never resolve.

    A redeploy is a routine event, so this is not an edge case; it is what
    happens every time somebody ships during working hours. Called once at
    startup: anything still claiming to be in flight cannot be, because
    nothing has started yet.

    Returns the ids it closed, so the caller can say how many in the log.
    """
    result = await session.execute(
        select(CallRow).where(
            CallRow.status.in_([CallStatus.TRANSCRIBING.value, CallStatus.ANALYZING.value])
        )
    )
    rows = list(result.scalars())

    for row in rows:
        row.status = CallStatus.FAILED.value
        data = dict(row.data)
        data["status"] = CallStatus.FAILED.value
        # Worded for the person who will read it on the call page. They did
        # nothing wrong and the fix is simply to upload it again.
        data["error"] = (
            "Analysis was interrupted when the server restarted. "
            "The recording is safe -- upload it again to re-run the analysis."
        )
        row.data = data

    if rows:
        await session.commit()
    return [row.id for row in rows]


async def list_calls(
    session: AsyncSession,
    org_id: str,
    *,
    rep_id: Optional[str] = None,
    deal_id: Optional[str] = None,
    limit: int = 200,
) -> list[Call]:
    query = select(CallRow).where(CallRow.org_id == org_id)
    if rep_id:
        query = query.where(CallRow.rep_id == rep_id)
    if deal_id:
        query = query.where(CallRow.deal_id == deal_id)
    query = query.order_by(CallRow.occurred_at.desc()).limit(limit)
    rows = (await session.execute(query)).scalars()
    return [Call.model_validate(r.data) for r in rows]


async def call_scores(session: AsyncSession, org_id: str) -> dict[str, float]:
    rows = (
        await session.execute(
            select(CallRow.id, CallRow.score).where(CallRow.org_id == org_id)
        )
    ).all()
    return {call_id: score for call_id, score in rows}


# --------------------------------------------------------------------------
# Artifacts
# --------------------------------------------------------------------------


async def put_artifact(
    session: AsyncSession, call_id: str, kind: str, model: BaseModel
) -> None:
    await _upsert(
        session,
        ArtifactRow,
        {
            "call_id": call_id,
            "kind": kind,
            "data": _dump(model),
            "updated_at": utcnow(),
        },
    )


async def get_artifact(
    session: AsyncSession, call_id: str, kind: str, model: type[T]
) -> Optional[T]:
    row = await session.get(ArtifactRow, {"call_id": call_id, "kind": kind})
    if row is None:
        return None
    return model.model_validate(row.data)


async def get_artifacts_for(
    session: AsyncSession, call_ids: Sequence[str], kind: str
) -> dict[str, dict[str, Any]]:
    """Bulk fetch. Used by the report and leaderboard paths so that summarising
    two hundred calls stays one query instead of two hundred."""
    if not call_ids:
        return {}
    rows = (
        await session.execute(
            select(ArtifactRow).where(
                ArtifactRow.kind == kind, ArtifactRow.call_id.in_(list(call_ids))
            )
        )
    ).scalars()
    return {r.call_id: r.data for r in rows}


# --------------------------------------------------------------------------
# Plays
# --------------------------------------------------------------------------


async def put_play(
    session: AsyncSession, play: Play, embedding: Optional[Sequence[float]] = None
) -> None:
    values: dict[str, Any] = {
        "id": play.id,
        "org_id": play.org_id,
        "name": play.name,
        "kind": play.kind.value,
        "usage_count": play.usage_count,
        "data": _dump(play),
    }
    if embedding is not None:
        values["embedding"] = vectors.encode(embedding)
    await _upsert(session, PlayRow, values)


async def get_play(session: AsyncSession, play_id: str) -> Optional[Play]:
    row = await session.get(PlayRow, play_id)
    return Play.model_validate(row.data) if row else None


async def list_plays(session: AsyncSession, org_id: str) -> list[Play]:
    rows = (
        await session.execute(
            select(PlayRow)
            .where(PlayRow.org_id == org_id)
            .order_by(PlayRow.usage_count.desc())
        )
    ).scalars()
    return [Play.model_validate(r.data) for r in rows]


async def nearest_play(
    session: AsyncSession, org_id: str, embedding: Sequence[float], threshold: float
) -> Optional[tuple[Play, float]]:
    """Closest existing play above `threshold`.

    This is the dedup gate: a candidate that lands near an existing play becomes
    another instance of it rather than a near-duplicate entry, which is what
    keeps the library converging on a handful of named moves.
    """
    rows = [
        r
        for r in (
            await session.execute(
                select(PlayRow).where(
                    PlayRow.org_id == org_id, PlayRow.embedding.is_not(None)
                )
            )
        ).scalars()
        if r.embedding
    ]
    if not rows:
        return None

    ranked = vectors.top_k(embedding, [r.embedding for r in rows], k=1)
    if not ranked:
        return None
    index, score = ranked[0]
    if score < threshold:
        return None
    return Play.model_validate(rows[index].data), score


# --------------------------------------------------------------------------
# Moments (the RAG index)
# --------------------------------------------------------------------------


async def add_moments(session: AsyncSession, moments: Sequence[dict[str, Any]]) -> None:
    for moment in moments:
        payload = dict(moment)
        payload["embedding"] = vectors.encode(payload["embedding"])
        await _upsert(session, MomentRow, payload)


async def search_moments(
    session: AsyncSession,
    org_id: str,
    query_embedding: Sequence[float],
    *,
    kind: Optional[str] = None,
    outcome: Optional[str] = None,
    exclude_rep_id: Optional[str] = None,
    rep_ids: Optional[Sequence[str]] = None,
    k: int = 6,
    diversify: bool = True,
) -> list[tuple[dict[str, Any], float]]:
    """Filtered semantic search over conversational moments.

    Filtering happens in SQL before scoring, so "how did a *top performer* win a
    pricing objection" narrows to the right candidates first and the vector
    comparison stays cheap.
    """
    query = select(MomentRow).where(MomentRow.org_id == org_id)
    if kind:
        query = query.where(MomentRow.kind == kind)
    if outcome:
        query = query.where(MomentRow.outcome == outcome)
    if exclude_rep_id:
        query = query.where(MomentRow.rep_id != exclude_rep_id)
    if rep_ids:
        query = query.where(MomentRow.rep_id.in_(list(rep_ids)))

    rows = list((await session.execute(query)).scalars())
    if not rows:
        return []

    blobs = [r.embedding for r in rows]
    ranked = (
        vectors.mmr(query_embedding, blobs, k=k)
        if diversify
        else vectors.top_k(query_embedding, blobs, k=k)
    )

    results = []
    for index, score in ranked:
        row = rows[index]
        results.append(
            (
                {
                    "id": row.id,
                    "call_id": row.call_id,
                    "rep_id": row.rep_id,
                    "kind": row.kind,
                    "outcome": row.outcome,
                    "text": row.text,
                    **row.data,
                },
                score,
            )
        )
    return results


async def count_moments(session: AsyncSession, org_id: str) -> int:
    rows = (
        await session.execute(select(MomentRow.id).where(MomentRow.org_id == org_id))
    ).all()
    return len(rows)


# --------------------------------------------------------------------------
# Coaching, dojo, reports
# --------------------------------------------------------------------------


async def put_coaching_plan(
    session: AsyncSession, org_id: str, plan: CoachingPlan
) -> None:
    await _upsert(
        session,
        CoachingPlanRow,
        {
            "id": plan.id,
            "org_id": org_id,
            "rep_id": plan.rep_id,
            "data": _dump(plan),
            "created_at": utcnow(),
        },
    )


async def get_coaching_plan(
    session: AsyncSession, rep_id: str
) -> Optional[CoachingPlan]:
    row = (
        await session.execute(
            select(CoachingPlanRow)
            .where(CoachingPlanRow.rep_id == rep_id)
            .order_by(CoachingPlanRow.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return CoachingPlan.model_validate(row.data) if row else None


async def put_dojo_session(
    session: AsyncSession, org_id: str, dojo: DojoSession
) -> None:
    await _upsert(
        session,
        DojoSessionRow,
        {
            "id": dojo.id,
            "org_id": org_id,
            "rep_id": dojo.rep_id,
            "score": dojo.score.overall if dojo.score else 0.0,
            "data": _dump(dojo),
            "created_at": utcnow(),
        },
    )


async def get_dojo_session(
    session: AsyncSession, session_id: str
) -> Optional[DojoSession]:
    row = await session.get(DojoSessionRow, session_id)
    return DojoSession.model_validate(row.data) if row else None


async def dojo_session_is_ours(
    session: AsyncSession, session_id: str, org_id: str
) -> bool:
    """True for a new id too: the first save of a session is how it is created."""
    row = await session.get(DojoSessionRow, session_id)
    return row is None or row.org_id == org_id


async def get_coaching_plan_by_id(
    session: AsyncSession, plan_id: str
) -> Optional[CoachingPlan]:
    row = await session.get(CoachingPlanRow, plan_id)
    return CoachingPlan.model_validate(row.data) if row else None


async def list_dojo_sessions(
    session: AsyncSession, org_id: str, rep_id: Optional[str] = None, limit: int = 25
) -> list[DojoSession]:
    query = select(DojoSessionRow).where(DojoSessionRow.org_id == org_id)
    if rep_id:
        query = query.where(DojoSessionRow.rep_id == rep_id)
    rows = (
        await session.execute(
            query.order_by(DojoSessionRow.created_at.desc()).limit(limit)
        )
    ).scalars()
    # Sessions are saved from their first turn. One still in progress is not history.
    sessions = [DojoSession.model_validate(r.data) for r in rows]
    return [s for s in sessions if s.ended_at]


async def put_report(session: AsyncSession, report: CycleReport) -> None:
    await _upsert(
        session,
        ReportRow,
        {
            "id": report.id,
            "org_id": report.org_id,
            "cycle_label": report.cycle_label,
            "data": _dump(report),
            "created_at": utcnow(),
        },
    )


async def get_report(session: AsyncSession, report_id: str) -> Optional[CycleReport]:
    row = await session.get(ReportRow, report_id)
    return CycleReport.model_validate(row.data) if row else None


async def latest_report(session: AsyncSession, org_id: str) -> Optional[CycleReport]:
    row = (
        await session.execute(
            select(ReportRow)
            .where(ReportRow.org_id == org_id)
            .order_by(ReportRow.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return CycleReport.model_validate(row.data) if row else None


async def list_reports(session: AsyncSession, org_id: str) -> list[CycleReport]:
    rows = (
        await session.execute(
            select(ReportRow)
            .where(ReportRow.org_id == org_id)
            .order_by(ReportRow.created_at.desc())
        )
    ).scalars()
    return [CycleReport.model_validate(r.data) for r in rows]
