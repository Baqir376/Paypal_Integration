"""Coach agent output: the diagnosis, the script, and the drills.

The load-bearing idea is `SourceRef`. Every generated line traces to a real
moment in a real winning call by a real teammate. A rep can click any line and
hear the person who actually said it -- which is the difference between a
script they trust and a script they ignore.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from .common import SalixModel, SkillAxis


class SourceRef(SalixModel):
    play_id: Optional[str] = None
    play_name: str = ""
    call_id: Optional[str] = None
    segment_id: Optional[str] = None
    rep_name: str = ""
    quote: str = ""


class SkillGap(SalixModel):
    axis: SkillAxis
    rep_value: float
    top_value: float
    delta: float
    severity: str = "medium"
    explanation: str = Field(description="Concrete and specific, never generic")
    evidence_call_ids: list[str] = Field(default_factory=list)


class ScriptLine(SalixModel):
    speaker: str = Field(description="rep | buyer_expected")
    text: str
    note: str = Field(default="", description="Delivery guidance, kept short")
    source: Optional[SourceRef] = None


class ScriptSection(SalixModel):
    label: str
    purpose: str
    lines: list[ScriptLine] = Field(default_factory=list)


class GeneratedScript(SalixModel):
    id: str
    rep_id: str
    title: str
    scenario: str = Field(description="The exact situation this script is for")
    sections: list[ScriptSection] = Field(default_factory=list)
    grounded_in: list[SourceRef] = Field(default_factory=list)


class Drill(SalixModel):
    title: str
    axis: SkillAxis
    instruction: str
    success_criteria: str
    persona_hint: str = Field(
        default="", description="Seeds the Dojo buyer for this drill"
    )


class CoachingPlan(SalixModel):
    id: str
    rep_id: str
    rep_name: str = ""
    generated_at: str
    diagnosis: str = Field(description="The single sentence a manager would say")
    gaps: list[SkillGap] = Field(default_factory=list)
    prescribed_play_ids: list[str] = Field(default_factory=list)
    prescription_rationale: dict[str, str] = Field(default_factory=dict)
    script: Optional[GeneratedScript] = None
    drills: list[Drill] = Field(default_factory=list)
