"""The closing test: a roleplay against the plan the rep was just given.

Only the start is new. The turns and the ending use the Dojo's endpoints, because
the buyer, the streaming and the measurement should all be identical to practice.
`/dojo/end` sees the session's mode and adds the verdict.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..dojo.closing import MODE, buyer_brief
from ..dojo.engine import DojoEngine
from ..dojo.persona import build_persona
from ..schemas.common import SalixModel
from ..store import repo
from .deps import OrgId, Prov, Session, owned
from .dojo import _opening_line

router = APIRouter(prefix="/roleplay", tags=["roleplay"])


class RoleplayStart(SalixModel):
    rep_id: str
    #: "en", "ur-roman" or "ur". Anything else is treated as English.
    language: str = "en"


@router.post("/start")
async def start(
    session: Session, org_id: OrgId, providers: Prov, body: RoleplayStart
) -> dict:
    rep = owned(await repo.get_rep(session, body.rep_id), org_id, "rep", body.rep_id)

    plan = await repo.get_coaching_plan(session, body.rep_id)
    if plan is None or not plan.gaps:
        raise HTTPException(
            status_code=409,
            detail="There is no coaching plan to test yet. Analyse a call first.",
        )

    scenario = plan.script.scenario if plan.script else ""
    # Hard: this is the test, and the buyer has the objections that beat this rep.
    persona = await build_persona(
        session, org_id, body.rep_id, difficulty=3, scenario_hint=scenario
    )

    dojo = DojoEngine(providers).start(body.rep_id, persona, scenario, body.language)
    dojo.mode = MODE
    dojo.plan_id = plan.id
    dojo.brief = buyer_brief(plan)

    # Saved now, and from here on this copy is the session. See `dojo.authoritative`.
    await repo.put_dojo_session(session, org_id, dojo)
    await session.commit()

    return {
        "session": dojo.model_dump(mode="json"),
        "rep_name": rep.name,
        "plays": [],
        "opening": _opening_line(persona, dojo.language),
        "plan": plan.model_dump(mode="json"),
    }
