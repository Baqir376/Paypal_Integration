"""Transcriptionist -- audio to a role-assigned, diarized transcript.

Diarization tells us *that* there are two speakers; it does not tell us which
one is the salesperson. Everything downstream depends on getting that right,
because a flipped assignment inverts the talk ratio and turns a coaching report
into nonsense.

So role assignment runs as a scored vote over signals that are cheap and
robust -- who opens, who asks the questions, who says "our team" versus "our
platform" -- and only escalates to the language model when the vote is close.
That keeps the common case free and deterministic while still handling the
genuinely ambiguous call.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import Field

from ..providers.base import ASRResult, ProviderError
from ..schemas.call import Segment, Transcript
from ..schemas.common import Emotion, SalixModel, SpeakerRole
from ..metrics.engine import is_question
from .base import Agent

log = logging.getLogger("salix.transcriptionist")


# Phrases only a seller says. Weighted by how strongly they give the game away.
REP_MARKERS: tuple[tuple[str, float], ...] = (
    ("thanks for taking the time", 3.0),
    ("thanks for making the time", 3.0),
    ("let me walk you through", 3.0),
    ("walk you through", 2.0),
    ("our platform", 2.5),
    ("our product", 2.5),
    ("our customers", 2.5),
    ("we help", 2.0),
    ("what we do", 2.0),
    ("i can send", 1.5),
    ("i will send", 1.5),
    ("does that make sense", 1.5),
    ("happy to", 1.0),
    ("case study", 1.5),
    ("free trial", 1.5),
    ("pricing works", 2.0),
    ("book a", 1.5),
    ("follow up", 1.0),
    ("demo", 1.0),
)

# Phrases only a buyer says.
BUYER_MARKERS: tuple[tuple[str, float], ...] = (
    ("we currently use", 3.0),
    ("we already use", 3.0),
    ("our team", 2.0),
    ("my team", 2.0),
    ("we use", 2.0),
    ("our current", 2.5),
    ("too expensive", 2.5),
    ("out of our budget", 2.5),
    ("my boss", 2.0),
    ("sign off", 2.0),
    ("i would need to check", 2.0),
    ("send me", 1.5),
    ("how much does", 2.0),
    ("what does it cost", 2.0),
    ("we are looking at", 1.5),
)


class RoleVerdict(SalixModel):
    """LLM tie-break output when the heuristics are inconclusive."""

    rep_speaker_id: int = Field(description="The diarization id of the salesperson")
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(description="One sentence, citing what gave it away")


class Transcriptionist(Agent):
    name = "Transcriptionist"

    # Below this margin the heuristic vote is treated as a coin flip.
    DECISIVE_MARGIN = 4.0

    async def run(
        self,
        asr: ASRResult,
        call_id: str,
        *,
        rep_speaker_id: Optional[int] = None,
    ) -> Transcript:
        """Build the transcript. `rep_speaker_id` short-circuits detection when
        the uploader already told us which channel is the rep."""
        segments = self._to_segments(asr, call_id)
        if not segments:
            raise ValueError("transcription produced no segments")

        if rep_speaker_id is None:
            rep_speaker_id = await self._identify_rep(segments)

        for segment in segments:
            segment.role = (
                SpeakerRole.REP
                if segment.speaker_id == rep_speaker_id
                else SpeakerRole.BUYER
            )

        return Transcript(
            call_id=call_id, segments=segments, language=asr.language
        )

    # -- construction ----------------------------------------------------

    def _to_segments(self, asr: ASRResult, call_id: str) -> list[Segment]:
        segments: list[Segment] = []
        for index, sentence in enumerate(asr.sentences):
            segments.append(
                Segment(
                    id=f"s{index:04d}",
                    index=index,
                    speaker_id=sentence.speaker_id,
                    role=SpeakerRole.UNKNOWN,
                    start_ms=sentence.begin_time,
                    end_ms=sentence.end_time,
                    text=sentence.text.strip(),
                    emotion=self._map_emotion(sentence.emotion),
                )
            )
        return segments

    @staticmethod
    def _map_emotion(raw: Optional[str]) -> Optional[Emotion]:
        """Normalise the ASR emotion label onto our vocabulary.

        Qwen ASR returns free-form labels that vary by model version, so
        anything unrecognised becomes None rather than a wrong guess.
        """
        if not raw:
            return None
        table = {
            "happy": Emotion.POSITIVE, "positive": Emotion.POSITIVE,
            "excited": Emotion.ENGAGED, "engaged": Emotion.ENGAGED,
            "neutral": Emotion.NEUTRAL, "calm": Emotion.NEUTRAL,
            "sad": Emotion.HESITANT, "hesitant": Emotion.HESITANT,
            "fear": Emotion.HESITANT, "uncertain": Emotion.HESITANT,
            "angry": Emotion.FRUSTRATED, "frustrated": Emotion.FRUSTRATED,
            "disgust": Emotion.SKEPTICAL, "skeptical": Emotion.SKEPTICAL,
        }
        return table.get(raw.strip().lower())

    # -- role assignment -------------------------------------------------

    def score_speakers(self, segments: list[Segment]) -> dict[int, float]:
        """Score each diarization id on how rep-like it sounds.

        Positive means rep, negative means buyer. Scores are normalised by
        utterance count so a speaker does not win simply by talking more.
        """
        scores: dict[int, float] = {}
        counts: dict[int, int] = {}

        for segment in segments:
            sid = segment.speaker_id
            counts[sid] = counts.get(sid, 0) + 1
            text = segment.text.lower()
            score = scores.get(sid, 0.0)

            for phrase, weight in REP_MARKERS:
                if phrase in text:
                    score += weight
            for phrase, weight in BUYER_MARKERS:
                if phrase in text:
                    score -= weight

            # Reps drive discovery, so questions lean rep -- weakly, because a
            # buyer evaluating a product asks plenty of them too.
            if is_question(segment.text):
                score += 0.4

            scores[sid] = score

        # The first substantive utterance is usually the rep opening the call.
        for segment in segments:
            if len(segment.text.split()) >= 5:
                scores[segment.speaker_id] = scores.get(segment.speaker_id, 0.0) + 2.0
                break

        return {sid: scores.get(sid, 0.0) / max(1, counts.get(sid, 1)) ** 0.5
                for sid in counts}

    async def _identify_rep(self, segments: list[Segment]) -> int:
        speakers = sorted({s.speaker_id for s in segments})
        if len(speakers) == 1:
            return speakers[0]

        scores = self.score_speakers(segments)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best_id, best_score = ranked[0]
        runner_score = ranked[1][1] if len(ranked) > 1 else best_score - 99

        margin = best_score - runner_score
        if margin >= self.DECISIVE_MARGIN:
            log.info(
                "rep identified heuristically as speaker %s (margin %.1f)",
                best_id, margin,
            )
            return best_id

        log.info("heuristic margin only %.1f; asking the model", margin)
        try:
            return await self._ask_model(segments, speakers, best_id)
        except (ProviderError, Exception) as exc:  # noqa: BLE001
            log.warning("role tie-break failed (%s); keeping heuristic", exc)
            return best_id

    async def _ask_model(
        self, segments: list[Segment], speakers: list[int], fallback: int
    ) -> int:
        # The opening minutes carry almost all the signal, and keeping the
        # prompt short keeps this tie-break cheap.
        opening = [s for s in segments if s.start_ms < 240_000][:60] or segments[:60]
        rendered = "\n".join(
            f"SPEAKER {s.speaker_id}: {s.text}" for s in opening
        )

        verdict = await self.llm.structured(
            system=self.system_prompt(
                "Identify which diarized speaker is the salesperson and which is "
                "the prospective buyer. The salesperson is the one selling a "
                "product or service; the buyer is evaluating it.",
                cite=False,
            ),
            user=(
                f"Speaker ids present: {speakers}.\n\n"
                f"Opening of the call:\n\n{rendered}"
            ),
            schema=RoleVerdict,
            temperature=0.0,
            max_tokens=512,
        )

        if verdict.rep_speaker_id not in speakers:
            log.warning(
                "model chose speaker %s which is not present; keeping heuristic",
                verdict.rep_speaker_id,
            )
            return fallback

        log.info(
            "rep identified as speaker %s by model (%.2f): %s",
            verdict.rep_speaker_id, verdict.confidence, verdict.reason,
        )
        return verdict.rep_speaker_id
