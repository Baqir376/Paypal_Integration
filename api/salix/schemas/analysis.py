"""Call anatomy -- the Anatomist agent's typed output.

Every list here is evidence-bearing: the LLM returns segment ids, the pipeline
hydrates them against the real transcript, and any id that does not exist is
treated as a hallucination and sent back for a retry. See
`salix.agents.evidence` for the hydration and rejection logic.
"""

from __future__ import annotations

from typing import Optional

from pydantic import ConfigDict, Field

from .common import (
    CallStage,
    EvidenceRef,
    ObjectionCategory,
    SalixModel,
    Severity,
)


class StageSpan(SalixModel):
    stage: CallStage
    start_ms: int
    end_ms: int
    segment_ids: list[str] = Field(default_factory=list)


class Objection(SalixModel):
    # Models like to add a "stage" here. Ignoring it loses nothing, and refusing it costs
    # a full round trip to the model on every call where it happens.
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    category: ObjectionCategory
    text: str = Field(description="The objection in the buyer's own words")
    raised: EvidenceRef
    handled: bool
    handling_quality: int = Field(
        ge=0, le=5, description="0 = ignored, 5 = turned into a reason to buy"
    )
    handling: list[EvidenceRef] = Field(default_factory=list)
    note: str = ""


class MeddicItem(SalixModel):
    covered: bool
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    note: str = ""


class MeddicCoverage(SalixModel):
    """MEDDIC qualification coverage. Chosen over BANT because it is the
    enterprise standard and its six slots map cleanly onto discoverable
    conversational evidence."""

    metrics: MeddicItem
    economic_buyer: MeddicItem
    decision_criteria: MeddicItem
    decision_process: MeddicItem
    identify_pain: MeddicItem
    champion: MeddicItem

    def coverage_ratio(self) -> float:
        items = [
            self.metrics,
            self.economic_buyer,
            self.decision_criteria,
            self.decision_process,
            self.identify_pain,
            self.champion,
        ]
        return sum(1 for i in items if i.covered) / len(items)


class Commitment(SalixModel):
    text: str
    by_role: str
    evidence: EvidenceRef
    is_concrete: bool = Field(
        description="True only if it names a specific action AND a specific time"
    )


class NextStep(SalixModel):
    text: str
    evidence: Optional[EvidenceRef] = None
    has_date: bool = False
    is_mutual: bool = Field(
        default=False, description="Both sides committed, not just the rep"
    )


class BuyerSignal(SalixModel):
    kind: str = Field(description="interest | concern | blocker | buying_signal")
    text: str
    evidence: EvidenceRef
    weight: float = Field(default=0.5, ge=0.0, le=1.0)


class TalkTrackIssue(SalixModel):
    title: str
    severity: Severity
    explanation: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    better_move: str = Field(description="What a top performer would have said")


class CallAnalysis(SalixModel):
    call_id: str
    summary: str = Field(description="Three sentences, no filler, no praise")
    headline: str = Field(description="The one thing that decided this call")
    stages: list[StageSpan] = Field(default_factory=list)
    objections: list[Objection] = Field(default_factory=list)
    meddic: MeddicCoverage
    commitments: list[Commitment] = Field(default_factory=list)
    next_step: Optional[NextStep] = None
    buyer_signals: list[BuyerSignal] = Field(default_factory=list)
    issues: list[TalkTrackIssue] = Field(default_factory=list)
    strengths: list[TalkTrackIssue] = Field(
        default_factory=list, description="Same shape; `better_move` holds why it worked"
    )
