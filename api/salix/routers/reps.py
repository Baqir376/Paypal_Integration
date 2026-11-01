"""Reps: the leaderboard, the profile, and coaching."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.coach import Coach
from ..metrics import analytics
from ..schemas.common import SalixModel
from ..schemas.org import Rep
from ..store import repo
from .deps import OrgId, Prov, Session, require_owner

log = logging.getLogger("salix.routers.reps")

router = APIRouter(prefix="/reps", tags=["reps"])


class RepProfile(SalixModel):
    snapshot: dict
    calls: list[dict]
    coaching_plan: Optional[dict] = None
    plays_used: list[dict] = []
    dojo_sessions: list[dict] = []


class RepCreate(SalixModel):
    name: str
    role: str = "ae"
    quota: float = Field(default=0.0, ge=0)


class RepUpdate(SalixModel):
    name: Optional[str] = None
    role: Optional[str] = None
    quota: Optional[float] = Field(default=None, ge=0)


#: "Bilal's Call", "Bilal call" and "Bilal" all name the same person.
_CALL_SUFFIX = re.compile(r"(?:['\u2019]s)?\s+call$", re.IGNORECASE)
MAX_NAME = 80


def clean_name(raw: str) -> str:
    """A person's name out of whatever was typed, or a 422."""
    name = " ".join("".join(c for c in raw if c.isprintable()).split())
    if not name or len(name) > MAX_NAME:
        raise HTTPException(
            status_code=422,
            detail=f"A salesperson's name must be 1 to {MAX_NAME} characters.",
        )
    return name


def _initials(name: str) -> str:
    return "".join(part[0] for part in name.split()[:2]).upper()


def _named(reps: list[Rep], name: str) -> Optional[Rep]:
    return next((r for r in reps if r.name.casefold() == name.casefold()), None)


async def resolve_salesperson(
    session: AsyncSession, org_id: str, typed: str, *, may_change_team: bool = True
) -> Rep:
    """Find who an upload is for, adding them to the team if they are new.

    A lone first name matches a colleague's full name, because nobody types
    "Bilal Ahmed" for a call. Two Bilals is a question for the person typing,
    not something to guess: a wrong guess puts one rep's call on another's record.
    """
    name = clean_name(_CALL_SUFFIX.sub("", typed.strip()))
    reps = await repo.list_reps(session, org_id)

    only_the_owner = HTTPException(
        status_code=403,
        detail=f"{name} is not on the team, and only the team owner can add people.",
    )

    exact = _named(reps, name)
    if exact is not None:
        if exact.archived:
            if not may_change_team:
                raise only_the_owner
            exact.archived = False
            await repo.put_rep(session, exact)
            log.info("restored %s to the team", exact.name)
        return exact

    if " " not in name:
        matches = [
            r for r in reps
            if not r.archived and r.name.split()[0].casefold() == name.casefold()
        ]
        if len(matches) == 1:
            return matches[0]
        if matches:
            options = ", ".join(r.name for r in matches)
            raise HTTPException(
                status_code=409,
                detail=f"More than one {name} on the team: {options}. Use the full name.",
            )

    if not may_change_team:
        raise only_the_owner

    rep = Rep(
        id=f"rep_{uuid.uuid4().hex[:10]}",
        org_id=org_id,
        name=name,
        initials=_initials(name),
    )
    await repo.put_rep(session, rep)
    log.info("added %s to the team", rep.name)
    return rep


@router.get("", response_model=list[dict])
async def leaderboard(session: Session, org_id: OrgId) -> list[dict]:
    snapshots = await analytics.rep_snapshots(session, org_id)
    return [s.model_dump(mode="json") for s in snapshots]


@router.get("/archived", response_model=list[Rep])
async def archived_reps(session: Session, org_id: OrgId) -> list[Rep]:
    return [r for r in await repo.list_reps(session, org_id) if r.archived]


@router.post("", response_model=Rep, status_code=201, dependencies=[Depends(require_owner)])
async def add_rep(session: Session, org_id: OrgId, request: RepCreate) -> Rep:
    name = clean_name(request.name)
    existing = _named(await repo.list_reps(session, org_id), name)
    if existing is not None and not existing.archived:
        raise HTTPException(status_code=409, detail=f"{existing.name} is already on the team.")
    # Same person back again: their history comes with them.
    rep = existing or Rep(id=f"rep_{uuid.uuid4().hex[:10]}", org_id=org_id, name=name)
    rep.archived = False
    rep.name = name
    rep.initials = _initials(name)
    rep.role = request.role
    rep.quota = request.quota
    await repo.put_rep(session, rep)
    await session.commit()
    return rep


async def _own_rep(session: AsyncSession, org_id: str, rep_id: str) -> Rep:
    rep = await repo.get_rep(session, rep_id)
    if rep is None or rep.org_id != org_id:
        raise HTTPException(status_code=404, detail=f"No rep {rep_id}")
    return rep


@router.patch("/{rep_id}", response_model=Rep, dependencies=[Depends(require_owner)])
async def edit_rep(
    session: Session, org_id: OrgId, rep_id: str, request: RepUpdate
) -> Rep:
    rep = await _own_rep(session, org_id, rep_id)
    if request.name is not None:
        name = clean_name(request.name)
        clash = _named(await repo.list_reps(session, org_id), name)
        if clash is not None and clash.id != rep.id:
            raise HTTPException(status_code=409, detail=f"{clash.name} already exists.")
        rep.name = name
        rep.initials = _initials(name)
    if request.role is not None:
        rep.role = request.role
    if request.quota is not None:
        rep.quota = request.quota
    await repo.put_rep(session, rep)
    await session.commit()
    return rep


@router.delete("/{rep_id}", status_code=204, dependencies=[Depends(require_owner)])
async def remove_rep(session: Session, org_id: OrgId, rep_id: str) -> None:
    """Take someone off the team. Their calls stay, and they can be restored."""
    rep = await _own_rep(session, org_id, rep_id)
    rep.archived = True
    await repo.put_rep(session, rep)
    await session.commit()


@router.post("/{rep_id}/restore", response_model=Rep, dependencies=[Depends(require_owner)])
async def restore_rep(session: Session, org_id: OrgId, rep_id: str) -> Rep:
    rep = await _own_rep(session, org_id, rep_id)
    rep.archived = False
    await repo.put_rep(session, rep)
    await session.commit()
    return rep


@router.get("/{rep_id}", response_model=RepProfile)
async def rep_profile(session: Session, org_id: OrgId, rep_id: str) -> RepProfile:
    snapshots = await analytics.rep_snapshots(session, org_id, include_archived=True)
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
    rep = await _own_rep(session, org_id, rep_id)

    plan = await Coach(providers).run(session, org_id, rep)
    await session.commit()
    log.info("coaching plan generated for %s (%d gaps)", rep.name, len(plan.gaps))
    return plan.model_dump(mode="json")
