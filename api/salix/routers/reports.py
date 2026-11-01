"""End-of-cycle reports."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from ..agents.analyst import Analyst
from ..metrics import analytics
from ..metrics.deal import Calibration, calibrate
from ..schemas.common import CallOutcome
from ..store import repo
from .deps import OrgId, Prov, Session, owned

log = logging.getLogger("salix.routers.reports")

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
async def list_reports(session: Session, org_id: OrgId) -> list[dict]:
    return [r.model_dump(mode="json") for r in await repo.list_reports(session, org_id)]


@router.get("/latest")
async def latest_report(session: Session, org_id: OrgId) -> dict | None:
    report = await repo.latest_report(session, org_id)
    return report.model_dump(mode="json") if report else None


@router.post("/generate")
async def generate_report(
    session: Session, org_id: OrgId, providers: Prov, cycle_label: str = ""
) -> dict:
    """Aggregate the cycle and write the narrative. Runs synchronously; the
    caller is a person who pressed a button and wants the document."""
    report = await Analyst(providers).cycle_report(session, org_id, cycle_label)
    await session.commit()
    log.info("cycle report generated: %s", report.headline)
    return report.model_dump(mode="json")


@router.get("/deal-calibration", response_model=Calibration)
async def deal_calibration(session: Session, org_id: OrgId) -> Calibration:
    """Does the deal score predict this team's real outcomes?"""
    bundles = await analytics.load_bundles(session, org_id)
    return calibrate(
        [
            (b.scorecard.deal.score, b.call.outcome is CallOutcome.WON)
            for b in bundles
            if b.scorecard is not None
            and b.scorecard.deal is not None
            and b.call.outcome in (CallOutcome.WON, CallOutcome.LOST)
        ]
    )


@router.get("/{report_id}")
async def get_report(session: Session, org_id: OrgId, report_id: str) -> dict:
    report = owned(await repo.get_report(session, report_id), org_id, "report", report_id)
    return report.model_dump(mode="json")
