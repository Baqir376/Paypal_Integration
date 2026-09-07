"""Reps: the leaderboard, the profile, and coaching."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from ..agents.coach import Coach
from ..metrics import analytics
from ..schemas.common import SalixModel
from ..store import repo
from .deps import OrgId, Prov, Session

log = logging.getLogger("salix.routers.reps")

router = APIRouter(prefix="/reps", tags=["reps"])


class RepProfile(SalixModel):
    snapshot: dict
    calls: list[dict]
    coaching_plan: Optional[dict] = None
    plays_used: list[dict] = []
    dojo_sessions: list[dict] = []


@router.get("", response_model=list[dict])
async def leaderboard(session: Session, org_id: OrgId) -> list[dict]:
    snapshots = await analytics.rep_snapshots(session, org_id)
    return [s.model_dump(mode="json") for s in snapshots]


@router.get("/{rep_id}", response_model=RepProfile)
async def rep_profile(session: Session, org_id: OrgId, rep_id: str) -> RepProfile:
    snapshots = await analytics.rep_snapshots(session, org_id)
    snapshot = next((s for s in snapshots if s.rep.id == rep_id), None)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"No rep {rep_id}")

    bundles = await analytics.load_bundles(session, org_id, rep_id=rep_id)
    bundles.sort(key=lambda b: b.call.occurred_at, reverse=True)

    plays_used = []
    for play in await repo.list_plays(session, org_id):
        mine = [i for i in play.instances if i.rep_id == rep_id]
        if not mine:
            continue
        payload = play.model_dump(mode="json")
        payload["my_instances"] = [i.model_dump(mode="json") for i in mine]
        plays_used.append(payload)

    plan = await repo.get_coaching_plan(session, rep_id)
    sessions = await repo.list_dojo_sessions(session, org_id, rep_id=rep_id, limit=10)

    return RepProfile(
        snapshot=snapshot.model_dump(mode="json"),
        calls=[
            {
                **b.call.model_dump(mode="json"),
                "score": b.scorecard.overall if b.scorecard else None,
                "talk_ratio_rep": b.metrics.talk_ratio_rep if b.metrics else None,
                "longest_monologue_ms": (
                    b.metrics.longest_monologue_ms if b.metrics else None
                ),
                "headline": b.analysis.headline if b.analysis else "",
            }
            for b in bundles
        ],
        coaching_plan=plan.model_dump(mode="json") if plan else None,
        plays_used=plays_used,
        dojo_sessions=[s.model_dump(mode="json") for s in sessions],
    )


@router.post("/{rep_id}/coach")
async def generate_coaching_plan(
    session: Session, org_id: OrgId, providers: Prov, rep_id: str
) -> dict:
    """Run the Coach: diagnose the gaps, retrieve from winning calls, write the
    script. Synchronous, because the caller wants the plan, not a job id."""
    rep = await repo.get_rep(session, rep_id)
    if rep is None:
        raise HTTPException(status_code=404, detail=f"No rep {rep_id}")

    plan = await Coach(providers).run(session, org_id, rep)
    await session.commit()
    log.info("coaching plan generated for %s (%d gaps)", rep.name, len(plan.gaps))
    return plan.model_dump(mode="json")
