"""Salix domain contract.

These Pydantic models are the single source of truth for the whole system: the
FastAPI surface validates against them, the agents are constrained to emit
them, and scripts/gen_types.py compiles them into web/lib/types.ts so the
frontend cannot drift from the backend without breaking the build.
"""

from .analysis import (
    BuyerSignal,
    CallAnalysis,
    Commitment,
    MeddicCoverage,
    MeddicItem,
    NextStep,
    Objection,
    StageSpan,
    TalkTrackIssue,
)
from .call import Call, CallDetail, CallStatus, Segment, Transcript
from .coaching import (
    CoachingPlan,
    Drill,
    GeneratedScript,
    ScriptLine,
    ScriptSection,
    SkillGap,
    SourceRef,
)
from .common import (
    CallOutcome,
    CallStage,
    Citation,
    DealStage,
    Emotion,
    EvidenceRef,
    ObjectionCategory,
    PlayKind,
    RiskKind,
    SalixModel,
    Severity,
    SkillAxis,
    SpeakerRole,
)
from .deal import Deal, DealTrajectory, Risk, TrajectoryPoint
from .dojo import (
    BuyerPersona,
    ClosingAssessment,
    ClosingVerdict,
    CoachNudge,
    DojoScore,
    DojoSession,
    DojoTurn,
    GapResult,
    GapVerdict,
    PersonaObjection,
)
from .metrics import (
    AxisScore,
    CallMetrics,
    DealScore,
    Interruption,
    Monologue,
    Scorecard,
    TalkSlice,
)
from .org import Cycle, Org, Rep, RepSnapshot
from .pipeline import STAGE_AGENTS, STAGE_LABELS, PipelineEvent, StageKey, StageStatus
from .play import Play, PlayCandidate, PlayInstance
from .report import CycleReport, Finding, Recommendation, RepRow, TeamMetrics

__all__ = [
    "AxisScore", "BuyerPersona", "ClosingAssessment", "ClosingVerdict", "DealScore", "GapResult", "GapVerdict", "BuyerSignal", "Call", "CallAnalysis", "CallDetail",
    "CallMetrics", "CallOutcome", "CallStage", "CallStatus", "Citation", "CoachNudge",
    "CoachingPlan", "Commitment", "Cycle", "CycleReport", "Deal", "DealStage",
    "DealTrajectory", "DojoScore", "DojoSession", "DojoTurn", "Drill", "Emotion",
    "EvidenceRef", "Finding", "GeneratedScript", "Interruption", "MeddicCoverage",
    "MeddicItem", "Monologue", "NextStep", "Objection", "ObjectionCategory", "Org",
    "PersonaObjection", "PipelineEvent", "Play", "PlayCandidate", "PlayInstance",
    "PlayKind", "Recommendation", "Rep", "RepRow", "RepSnapshot", "Risk", "RiskKind",
    "SalixModel", "Scorecard", "ScriptLine", "ScriptSection", "Segment", "Severity",
    "SkillAxis", "SkillGap", "SourceRef", "SpeakerRole", "STAGE_AGENTS",
    "STAGE_LABELS", "StageKey", "StageSpan", "StageStatus", "TalkSlice",
    "TalkTrackIssue", "TeamMetrics", "Transcript", "TrajectoryPoint",
]
