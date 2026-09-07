"""The Dojo: live voice roleplay against a buyer built from the reps own
lost deals.

The persona is not invented. `derived_from_call_ids` points at the calls whose
objections were mined to build it, so a rep practising against "Ayesha" is
practising against the exact wall they actually hit.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from .common import ObjectionCategory, SalixModel, SkillAxis


class PersonaObjection(SalixModel):
    category: ObjectionCategory
    text: str
    from_call_id: Optional[str] = None
    hardness: float = Field(default=0.5, ge=0.0, le=1.0)


class BuyerPersona(SalixModel):
    id: str
    name: str
    title: str
    company: str
    disposition: str = Field(description="e.g. guarded, time-poor, data-driven")
    context: str = Field(description="What they know and want going in")
    objections: list[PersonaObjection] = Field(default_factory=list)
    voice: str = Field(default="", description="TTS voice id")
    voice_instruction: str = Field(
        default="", description="Prosody control passed to Qwen TTS"
    )
    derived_from_call_ids: list[str] = Field(default_factory=list)
    difficulty: int = Field(default=2, ge=1, le=3)


class DojoTurn(SalixModel):
    index: int
    speaker: str = Field(description="rep | buyer")
    text: str
    start_ms: int = 0
    end_ms: int = 0
    audio_url: Optional[str] = None


class CoachNudge(SalixModel):
    """A live hint on the coach rail. Fired mid-session, never after."""

    at_turn: int
    kind: str = Field(description="play | warning | praise")
    title: str
    detail: str
    play_id: Optional[str] = None


class DojoScore(SalixModel):
    overall: float = Field(ge=0.0, le=100.0)
    axes: dict[SkillAxis, float] = Field(default_factory=dict)
    objections_faced: int = 0
    objections_handled: int = 0
    plays_landed: list[str] = Field(default_factory=list)
    plays_missed: list[str] = Field(default_factory=list)
    verdict: str = ""
    talk_ratio_rep: float = Field(default=0.0, ge=0.0, le=1.0)


class DojoSession(SalixModel):
    id: str
    rep_id: str
    persona: BuyerPersona
    #: What the buyer answers in: "en" or "ur-roman".
    #:
    #: Carried on the session rather than inferred per turn, because inference
    #: is wrong exactly when it matters. Roman Urdu is Latin script, so a short
    #: turn like "ok, aur?" is indistinguishable from English by any script
    #: test -- and a buyer who answers that in English has broken the exercise
    #: for a rep practising Urdu.
    language: str = "en"
    scenario: str = ""
    started_at: str = ""
    ended_at: Optional[str] = None
    turns: list[DojoTurn] = Field(default_factory=list)
    nudges: list[CoachNudge] = Field(default_factory=list)
    score: Optional[DojoScore] = None
