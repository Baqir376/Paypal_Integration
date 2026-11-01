"""Deals: the trajectory of a sales cycle and its risk radar."""

from __future__ import annotations

from fastapi import APIRouter

from ..agents.analyst import Analyst
from ..store import repo
from .deps import OrgId, Prov, Session, owned

router = APIRouter(prefix="/deals", tags=["deals"])


@router.get("")
async def list_deals(session: Session, org_id: OrgId, providers: Prov) -> list[dict]:
    """Every deal with its computed trajectory.

    Trajectories are derived on read rather than stored, so the radar always
    reflects the most recently analysed call instead of the last time a report
    was generated.
    """
    deals = await repo.list_deals(session, org_id)
    reps = {r.id: r.name for r in await repo.list_reps(session, org_id)}
    analyst = Analyst(providers)

    payload = []
    for deal in deals:
        trajectory = await analyst.trajectory(
            session, deal, reps.get(deal.owner_id, "")
        )
        payload.append(
            {
                "deal": deal.model_dump(mode="json"),
                "owner_name": reps.get(deal.owner_id, ""),
                "trajectory": trajectory.model_dump(mode="json"),
            }
        )
    payload.sort(key=lambda d: d["trajectory"]["health"])
    return payload


@router.get("/{deal_id}")
async def get_deal(
    session: Session, org_id: OrgId, providers: Prov, deal_id: str
) -> dict:
    deal = owned(await repo.get_deal(session, deal_id), org_id, "deal", deal_id)

    reps = {r.id: r.name for r in await repo.list_reps(session, org_id)}
    trajectory = await Analyst(providers).trajectory(
        session, deal, reps.get(deal.owner_id, "")
    )
    calls = await repo.list_calls(session, org_id, deal_id=deal_id)

    return {
        "deal": deal.model_dump(mode="json"),
        "owner_name": reps.get(deal.owner_id, ""),
        "trajectory": trajectory.model_dump(mode="json"),
        "calls": [c.model_dump(mode="json") for c in calls],
    }
