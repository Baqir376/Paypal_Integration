"""Shared enums and evidence primitives.

Every LLM-produced claim in Salix must point back at the transcript it came
from. `EvidenceRef` is how it does that, and the validators in the analysis
schemas reject findings that arrive without one.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SalixModel(BaseModel):
    """Base model: strict about unknown keys so a drifting LLM response fails
    loudly at parse time rather than silently losing a field."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SpeakerRole(str, Enum):
    REP = "rep"
    BUYER = "buyer"
    UNKNOWN = "unknown"


class CallOutcome(str, Enum):
    WON = "won"
    LOST = "lost"
    OPEN = "open"


class DealStage(str, Enum):
    DISCOVERY = "discovery"
    DEMO = "demo"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class CallStage(str, Enum):
    """Coarse phases of a sales conversation, in canonical order."""

    OPENER = "opener"
    DISCOVERY = "discovery"
    PITCH = "pitch"
    OBJECTION = "objection"
    NEGOTIATION = "negotiation"
    CLOSE = "close"
    NEXT_STEPS = "next_steps"


class ObjectionCategory(str, Enum):
    PRICE = "price"
    TIMING = "timing"
    AUTHORITY = "authority"
    COMPETITION = "competition"
    STATUS_QUO = "status_quo"
    TRUST = "trust"
    FIT = "fit"
    RISK = "risk"
    OTHER = "other"


class PlayKind(str, Enum):
    STORY_ARC = "story_arc"
    ANALOGY = "analogy"
    PROOF_POINT = "proof_point"
    REFRAME = "reframe"
    QUESTION_SEQUENCE = "question_sequence"
    OBJECTION_TURN = "objection_turn"


class RiskKind(str, Enum):
    UNRESOLVED_OBJECTION = "unresolved_objection"
    NO_NEXT_STEP = "no_next_step"
    SINGLE_THREADED = "single_threaded"
    MOMENTUM_DECAY = "momentum_decay"
    MONOLOGUE_DOMINANCE = "monologue_dominance"
    CHAMPION_SILENT = "champion_silent"
    NO_ECONOMIC_BUYER = "no_economic_buyer"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Emotion(str, Enum):
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    ENGAGED = "engaged"
    HESITANT = "hesitant"
    FRUSTRATED = "frustrated"
    SKEPTICAL = "skeptical"


class SkillAxis(str, Enum):
    """The six axes of the rep radar. Each maps to a deterministic sub-score
    plus, where relevant, an LLM-judged component."""

    LISTENING = "listening"
    DISCOVERY = "discovery"
    STORYTELLING = "storytelling"
    OBJECTION_HANDLING = "objection_handling"
    PACE_AND_PRESENCE = "pace_and_presence"
    CLOSING = "closing"


class EvidenceRef(SalixModel):
    """A pointer into the transcript. `quote` is verbatim so the UI can render
    the claim and its proof side by side without a second lookup."""

    segment_id: str = Field(description="Segment id, e.g. 's0042'")
    call_id: Optional[str] = None
    quote: str = Field(default="", description="Verbatim text from that segment")
    start_ms: Optional[int] = None


class Citation(SalixModel):
    """What the LLM is required to return: bare segment ids. The pipeline
    hydrates these into full EvidenceRefs against the real transcript, which is
    also how we detect a hallucinated id."""

    segment_ids: list[str] = Field(default_factory=list, min_length=0)
