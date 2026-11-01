"""Pipeline progress events, streamed to the browser over SSE.

The ingest screen renders the analysis DAG live from these, which is both a
useful progress indicator and the clearest possible demonstration that there is
a real multi-stage system behind the button.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import Field

from .common import SalixModel


class StageKey(str, Enum):
    UPLOAD = "upload"
    TRANSCRIBE = "transcribe"
    DIARIZE = "diarize"
    METRICS = "metrics"
    ANATOMY = "anatomy"
    PLAYS = "plays"
    EMBED = "embed"
    TRAJECTORY = "trajectory"
    COACH = "coach"
    DONE = "done"


STAGE_LABELS: dict[StageKey, str] = {
    StageKey.UPLOAD: "Securing audio",
    StageKey.TRANSCRIBE: "Transcribing",
    StageKey.DIARIZE: "Separating speakers",
    StageKey.METRICS: "Measuring conversation",
    StageKey.ANATOMY: "Reading call anatomy",
    StageKey.PLAYS: "Extracting narrative plays",
    StageKey.EMBED: "Indexing moments",
    StageKey.TRAJECTORY: "Updating deal trajectory",
    StageKey.COACH: "Writing the coaching plan",
    StageKey.DONE: "Complete",
}

STAGE_AGENTS: dict[StageKey, str] = {
    StageKey.UPLOAD: "ingest",
    StageKey.TRANSCRIBE: "Transcriptionist",
    StageKey.DIARIZE: "Transcriptionist",
    StageKey.METRICS: "Prosodist",
    StageKey.ANATOMY: "Anatomist",
    StageKey.PLAYS: "Playwright",
    StageKey.EMBED: "Playwright",
    StageKey.TRAJECTORY: "Analyst",
    StageKey.COACH: "Coach",
    StageKey.DONE: "-",
}


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineEvent(SalixModel):
    call_id: str
    stage: StageKey
    status: StageStatus
    label: str = ""
    agent: str = ""
    detail: str = ""
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    elapsed_ms: int = 0
    payload: Optional[dict[str, Any]] = None
