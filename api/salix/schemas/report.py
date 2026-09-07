"""End-of-cycle team report -- the Analyst agent's deliverable."""

from __future__ import annotations

from pydantic import Field

from .common import SalixModel, SkillAxis
from .deal import Risk


class RepRow(SalixModel):
    rep_id: str
    name: str
    calls: int
    deals: int
    won: int
    lost: int
    win_rate: float = Field(ge=0.0, le=1.0)
    revenue: float = 0.0
    overall_score: float = Field(ge=0.0, le=100.0)
    axes: dict[SkillAxis, float] = Field(default_factory=dict)
    trend: float = Field(default=0.0, description="Score delta vs. previous cycle")
    standout: str = ""
    watch_item: str = ""


class TeamMetrics(SalixModel):
    calls_analyzed: int
    hours_analyzed: float
    deals: int
    win_rate: float = Field(ge=0.0, le=1.0)
    pipeline_value: float = 0.0
    closed_value: float = 0.0
    avg_talk_ratio: float = Field(ge=0.0, le=1.0)
    avg_patience_ms: float = 0.0
    avg_meddic_coverage: float = Field(ge=0.0, le=1.0)
    objection_resolution_rate: float = Field(ge=0.0, le=1.0)
    next_step_rate: float = Field(ge=0.0, le=1.0)


class Finding(SalixModel):
    title: str
    detail: str
    impact: str = Field(description="Quantified where the data supports it")
    supporting_call_ids: list[str] = Field(default_factory=list)


class Recommendation(SalixModel):
    title: str
    detail: str
    owner: str = ""
    expected_lift: str = ""
    priority: int = Field(default=2, ge=1, le=3)


class CycleReport(SalixModel):
    id: str
    org_id: str
    cycle_label: str
    period_start: str
    period_end: str
    headline: str = Field(description="One line a VP would forward")
    narrative: str = Field(description="The story of the cycle, in prose")
    team: TeamMetrics
    reps: list[RepRow] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    top_play_ids: list[str] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    generated_at: str = ""
