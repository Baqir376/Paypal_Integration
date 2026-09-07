"""The Winning-DNA playbook.

A `Play` is a named, reusable narrative move lifted out of calls that closed.
It is not advice -- it is a move somebody on this team actually made, with the
transcript to prove it and a measured win-rate delta attached.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from .common import EvidenceRef, PlayKind, SalixModel


class PlayInstance(SalixModel):
    """One observed use of a play in a real call."""

    id: str
    play_id: str
    call_id: str
    rep_id: str
    rep_name: str = ""
    account: str = ""
    outcome: str = "open"
    quote: str = Field(description="The verbatim passage where the play lands")
    evidence: list[EvidenceRef] = Field(default_factory=list)
    effectiveness: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How well it worked here, judged on the buyer's response",
    )


class Play(SalixModel):
    id: str
    org_id: str
    name: str = Field(
        description="Short, memorable, title-cased. e.g. 'The Compounding Cost'"
    )
    kind: PlayKind
    thesis: str = Field(description="One sentence: what this move does to a buyer")
    when_to_use: str
    beats: list[str] = Field(
        default_factory=list, description="The structural steps, in order"
    )
    template: str = Field(
        default="", description="A say-this-way rendering, with [BRACKETED] slots"
    )
    origin_rep_id: Optional[str] = None
    origin_rep_name: str = ""
    instances: list[PlayInstance] = Field(default_factory=list)

    usage_count: int = 0
    win_rate_with: Optional[float] = None
    win_rate_without: Optional[float] = None

    @property
    def win_rate_lift(self) -> Optional[float]:
        if self.win_rate_with is None or self.win_rate_without is None:
            return None
        return round(self.win_rate_with - self.win_rate_without, 3)


class PlayCandidate(SalixModel):
    """Raw Playwright output before dedup against the existing library.

    Deliberately thinner than `Play`: the merge step decides whether this
    becomes a new play or another instance of one we already know.
    """

    name: str
    kind: PlayKind
    thesis: str
    when_to_use: str
    beats: list[str] = Field(default_factory=list)
    template: str = ""
    quote: str
    segment_ids: list[str] = Field(default_factory=list, min_length=1)
    effectiveness: float = Field(default=0.5, ge=0.0, le=1.0)
