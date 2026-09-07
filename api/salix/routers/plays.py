"""The playbook: the narrative DNA mined from calls that closed."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..store import repo
from .deps import OrgId, Session

router = APIRouter(prefix="/plays", tags=["plays"])


@router.get("")
async def list_plays(session: Session, org_id: OrgId) -> list[dict]:
    plays = await repo.list_plays(session, org_id)
    reps = {r.id: r.name for r in await repo.list_reps(session, org_id)}

    payload = []
    for play in plays:
        item = play.model_dump(mode="json")
        item["win_rate_lift"] = play.win_rate_lift
        item["used_by"] = sorted(
            {reps.get(i.rep_id, i.rep_name) for i in play.instances if i.rep_id}
        )
        item["won_with"] = sum(1 for i in play.instances if i.outcome == "won")
        payload.append(item)
    return payload


@router.get("/{play_id}")
async def get_play(session: Session, org_id: OrgId, play_id: str) -> dict:
    play = await repo.get_play(session, play_id)
    if play is None:
        raise HTTPException(status_code=404, detail=f"No play {play_id}")

    reps = {r.id: r.name for r in await repo.list_reps(session, org_id)}
    calls = {c.id: c for c in await repo.list_calls(session, org_id, limit=1000)}

    item = play.model_dump(mode="json")
    item["win_rate_lift"] = play.win_rate_lift
    # Each instance is hydrated with its call so the UI can link straight to
    # the moment rather than making the reader hunt for it.
    item["instances"] = [
        {
            **instance.model_dump(mode="json"),
            "rep_name": reps.get(instance.rep_id, instance.rep_name),
            "call_title": calls[instance.call_id].title
            if instance.call_id in calls
            else "",
            "occurred_at": calls[instance.call_id].occurred_at.isoformat()
            if instance.call_id in calls
            else None,
        }
        for instance in play.instances
    ]
    return item
