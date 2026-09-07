"""Deals and their trajectory across a sales cycle.

A single call tells you how a conversation went. A deal tells you whether the
*sequence* of conversations is going anywhere -- which is where the money is.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from .common import CallOutcome, DealStage, EvidenceRef, RiskKind, SalixModel, Severity


class Deal(SalixModel):
    id: str
    org_id: str
    name: str
    account: str
    owner_id: str
    value: float = 0.0
    stage: DealStage = DealStage.DISCOVERY
    outcome: CallOutcome = CallOutcome.OPEN
    opened_at: datetime
    closed_at: Optional[datetime] = None
    contacts: list[str] = Field(default_factory=list)


class Risk(SalixModel):
    kind: RiskKind
    severity: Severity
    title: str
    explanation: str = Field(
        description="Names the cause, not the symptom. Cites which call."
    )
    evidence: list[EvidenceRef] = Field(default_factory=list)
    first_seen_call_id: Optional[str] = None
    age_days: int = 0


class TrajectoryPoint(SalixModel):
    call_id: str
    occurred_at: datetime
    title: str
    score: float = Field(ge=0.0, le=100.0)
    buyer_engagement: float = Field(ge=0.0, le=1.0)
    open_objections: int = 0
    had_next_step: bool = False
    meddic_coverage: float = Field(default=0.0, ge=0.0, le=1.0)


class DealTrajectory(SalixModel):
    deal_id: str
    deal_name: str = ""
    account: str = ""
    owner_name: str = ""
    value: float = 0.0
    stage: DealStage = DealStage.DISCOVERY
    points: list[TrajectoryPoint] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    momentum: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Slope of buyer engagement across the last three calls",
    )
    health: float = Field(default=50.0, ge=0.0, le=100.0)
    verdict: str = ""
