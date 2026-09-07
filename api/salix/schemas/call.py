"""Calls, transcripts and segments.

A `Segment` mirrors one sentence from the Model Studio ASR result
(`transcripts[].sentences[]` -> begin_time / end_time / text / speaker_id),
enriched with the role assignment and derived word counts we compute locally.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import ConfigDict, Field, computed_field

from .common import CallOutcome, Emotion, SalixModel, SpeakerRole


class Segment(SalixModel):
    # Computed fields are serialized for the frontend but must not be rejected
    # when the same JSON is read back, so this one model relaxes `extra`.
    # Segments come from ASR parsing, never from an LLM, so nothing is lost.
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = Field(description="Stable within a call, e.g. 's0042'")
    index: int
    speaker_id: int = Field(description="Raw diarization label from ASR")
    role: SpeakerRole = SpeakerRole.UNKNOWN
    start_ms: int
    end_ms: int
    text: str
    emotion: Optional[Emotion] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @computed_field  # type: ignore[prop-decorator]
    @property
    def wpm(self) -> float:
        """Words per minute for this utterance. Sub-second fragments are noisy,
        so they report 0 rather than a wild extrapolation."""
        if self.duration_ms < 1000:
            return 0.0
        return round(self.word_count / (self.duration_ms / 60000.0), 1)


class Transcript(SalixModel):
    call_id: str
    segments: list[Segment] = Field(default_factory=list)
    language: str = "en"

    def by_id(self, segment_id: str) -> Optional[Segment]:
        return next((s for s in self.segments if s.id == segment_id), None)

    def rep_segments(self) -> list[Segment]:
        return [s for s in self.segments if s.role is SpeakerRole.REP]

    def buyer_segments(self) -> list[Segment]:
        return [s for s in self.segments if s.role is SpeakerRole.BUYER]

    def render(self, with_ids: bool = True) -> str:
        """Flatten to the form the LLM sees. Ids are inlined so the model can
        cite them, and timestamps so it can reason about pacing."""
        lines = []
        for s in self.segments:
            stamp = f"{s.start_ms // 60000:02d}:{(s.start_ms // 1000) % 60:02d}"
            prefix = f"[{s.id}] " if with_ids else ""
            lines.append(f"{prefix}({stamp}) {s.role.value.upper()}: {s.text}")
        return "\n".join(lines)


class CallStatus(str, Enum):
    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


class Call(SalixModel):
    id: str
    org_id: str
    deal_id: Optional[str] = None
    rep_id: str
    title: str
    account: str
    occurred_at: datetime
    duration_ms: int = 0
    audio_url: Optional[str] = None
    status: CallStatus = CallStatus.UPLOADED
    outcome: CallOutcome = CallOutcome.OPEN
    error: Optional[str] = None


class CallDetail(SalixModel):
    """Everything the call page needs, in one round trip."""

    call: Call
    transcript: Transcript
    metrics: Optional[dict] = None
    analysis: Optional[dict] = None
    plays: list[dict] = Field(default_factory=list)
