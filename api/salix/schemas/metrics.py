"""Deterministic conversation metrics.

Nothing in this module is inferred by a language model. Every value is computed
in Python from diarized millisecond timestamps, which is what makes the numbers
defensible -- and what makes them unit-testable against hand-computed fixtures.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from .common import SalixModel, SkillAxis


class TalkSlice(SalixModel):
    """One bucket of the talk timeline, used to drive the Conversation Helix.

    `rep_share` is the fraction of *speech* in the bucket owned by the rep, so a
    bucket of pure silence reports 0.5 (nobody holds the floor) rather than
    biasing the ribbon toward whoever happened to speak last.
    """

    start_ms: int
    end_ms: int
    rep_ms: int
    buyer_ms: int
    rep_share: float = Field(ge=0.0, le=1.0)
    energy: float = Field(ge=0.0, le=1.0, description="Normalized speech density")


class Monologue(SalixModel):
    speaker_role: str
    start_ms: int
    end_ms: int
    duration_ms: int
    segment_ids: list[str] = Field(default_factory=list)
    opening_words: str = ""


class Interruption(SalixModel):
    at_ms: int
    by_role: str
    segment_id: str
    overlap_ms: int


class CallMetrics(SalixModel):
    call_id: str
    duration_ms: int

    # --- Floor control -------------------------------------------------
    rep_talk_ms: int = 0
    buyer_talk_ms: int = 0
    silence_ms: int = 0
    talk_ratio_rep: float = Field(default=0.0, ge=0.0, le=1.0)
    longest_monologue_ms: int = 0
    longest_monologue_at_ms: int = 0
    monologues_over_threshold: int = 0
    monologues: list[Monologue] = Field(default_factory=list)

    # --- Reciprocity ---------------------------------------------------
    patience_ms: float = Field(
        default=0.0,
        description="Mean pause the rep leaves after the buyer stops speaking",
    )
    switches_per_min: float = 0.0
    interruptions_by_rep: int = 0
    interruptions_by_buyer: int = 0
    interruptions: list[Interruption] = Field(default_factory=list)

    # --- Discovery -----------------------------------------------------
    rep_question_count: int = 0
    rep_question_rate_per_min: float = 0.0
    open_question_ratio: float = Field(default=0.0, ge=0.0, le=1.0)

    # --- Delivery ------------------------------------------------------
    rep_wpm: float = 0.0
    buyer_wpm: float = 0.0
    language: str = Field(
        default="en",
        description=(
            "Dominant language of the rep's speech: 'en', 'ur' or 'ur-roman'. "
            "Pace is judged against a band calibrated for it, because words "
            "per minute is not comparable across languages."
        ),
    )
    filler_rate_rep: float = Field(
        default=0.0, description="Filler words per 100 rep words"
    )
    longest_dead_air_ms: int = 0

    # --- Shape ---------------------------------------------------------
    timeline: list[TalkSlice] = Field(default_factory=list)


class AxisScore(SalixModel):
    axis: SkillAxis
    score: float = Field(ge=0.0, le=100.0)
    benchmark: float = Field(ge=0.0, le=100.0, description="Top-performer value")
    drivers: list[str] = Field(
        default_factory=list, description="Plain-language reasons for the score"
    )


class DealScore(SalixModel):
    """Where the deal stands after this call. See metrics/deal.py."""

    score: float = Field(ge=0.0, le=100.0)
    band: str = Field(description="strong | at risk | weak")
    drivers: list[str] = Field(default_factory=list)


class Scorecard(SalixModel):
    """Metrics translated onto a 0-100 scale against published benchmarks.

    Kept separate from `CallMetrics` on purpose: the metrics are facts, the
    scorecard is an opinion about them, and only the latter should change when
    we retune a benchmark.
    """

    call_id: str
    overall: float = Field(ge=0.0, le=100.0)
    axes: list[AxisScore] = Field(default_factory=list)
    deal: Optional[DealScore] = None
    caveats: list[str] = Field(
        default_factory=list,
        description="Why this score should be read with care. Empty when it is sound.",
    )

    def axis(self, axis: SkillAxis) -> float:
        return next((a.score for a in self.axes if a.axis is axis), 0.0)
