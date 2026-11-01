"""Organisation, people and cycles."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from .common import SalixModel, SkillAxis


class Rep(SalixModel):
    id: str
    org_id: str
    name: str
    role: str = "ae"
    initials: str = ""
    quota: float = 0.0
    attained: float = 0.0
    joined_at: str = ""
    is_top_performer: bool = False
    #: Removed from the team. Their calls stay: colleagues' coaching plans cite
    #: them and the team's history is computed from them.
    archived: bool = False


class RepSnapshot(SalixModel):
    """Rolled-up view of a rep for the leaderboard and profile header."""

    rep: Rep
    calls: int = 0
    deals: int = 0
    won: int = 0
    lost: int = 0
    win_rate: float = 0.0
    overall_score: float = 0.0
    axes: dict[SkillAxis, float] = Field(default_factory=dict)
    team_axes: dict[SkillAxis, float] = Field(default_factory=dict)
    trend: list[float] = Field(default_factory=list)
    talk_ratio: float = 0.0
    patience_ms: float = 0.0
    rank: int = 0


class Org(SalixModel):
    id: str
    name: str
    product: str = ""
    icp: str = Field(default="", description="Ideal customer profile, one line")
    cycle_label: str = ""


class Cycle(SalixModel):
    id: str
    org_id: str
    label: str
    start: str
    end: str
    is_current: bool = False
    target: float = 0.0
    closed: float = 0.0
