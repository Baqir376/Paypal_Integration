"""The analysis DAG.

One call moves through the graph below. Each stage is owned by one agent, has a
typed output, is persisted the moment it completes, and reports its status to
the event bus so the browser can watch the graph light up.

    Transcriptionist ──► Prosodist ──► Anatomist ──► Playwright ──► Analyst
      ASR + roles        (no LLM)       anatomy       plays +        deal
                             │                        moments     trajectory
                             └────── provisional scorecard ──────┘

Two design decisions worth stating:

**Stages persist as they finish.** The call page is useful while the language
models are still working -- transcript first, then measured numbers, then
interpretation. Nothing waits for everything.

**Degradation is per stage.** If the Playwright fails, the call still has a
transcript, metrics and an anatomy; it simply contributes no plays. Only
transcription is fatal, because without it there is nothing to analyse. A
hackathon demo does not get to show an error page because one model call
timed out.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..agents.analyst import Analyst
from ..agents.anatomist import Anatomist
from ..agents.playwright import Playwright
from ..agents.prosodist import Prosodist
from ..agents.transcriptionist import Transcriptionist
from ..providers.base import Providers
from .romanise import romanise
from ..schemas.analysis import CallAnalysis
from ..schemas.call import Call, CallStatus, Transcript
from ..schemas.metrics import CallMetrics, Scorecard
from ..schemas.pipeline import StageKey, StageStatus
from ..schemas.play import Play
from ..agents.evidence import citation_coverage
from ..store import repo, session_scope
from .bus import bus

log = logging.getLogger("salix.pipeline")


@dataclass
class PipelineResult:
    call: Call
    transcript: Optional[Transcript] = None
    metrics: Optional[CallMetrics] = None
    scorecard: Optional[Scorecard] = None
    analysis: Optional[CallAnalysis] = None
    plays: list[Play] = field(default_factory=list)
    failed_stages: list[str] = field(default_factory=list)
    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.transcript is not None


class Pipeline:
    def __init__(self, providers: Providers):
        self.providers = providers
        self.transcriptionist = Transcriptionist(providers)
        self.prosodist = Prosodist(providers)
        self.anatomist = Anatomist(providers)
        self.playwright = Playwright(providers)
        self.analyst = Analyst(providers)

    async def run(
        self,
        session: AsyncSession,
        call: Call,
        *,
        audio_url: Optional[str] = None,
        rep_speaker_id: Optional[int] = None,
        rep_name: str = "",
        deal_context: str = "",
        language: str = "",
    ) -> PipelineResult:
        started = time.monotonic()
        result = PipelineResult(call=call)

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        # -- Transcription (fatal on failure) ---------------------------
        await bus.emit(call.id, StageKey.TRANSCRIBE, StageStatus.RUNNING, progress=0.05)
        try:
            # Whoever uploaded the recording knows what language it was in;
            # nothing else does. Guessing produced the worst possible failure
            # -- an Urdu call transcribed into Devanagari, which the metrics
            # engine reads as English, so it was scored against English pace
            # benchmarks and the Urdu question detection never ran. Wrong
            # numbers with no error anywhere.
            asr = await self.providers.asr.transcribe(
                audio_url or call.audio_url or "",
                diarize=True,
                language_hints=(language,) if language else (),
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("transcription failed for %s", call.id)
            await bus.emit(
                call.id, StageKey.TRANSCRIBE, StageStatus.FAILED,
                detail=str(exc)[:300], elapsed_ms=elapsed(),
            )
            await repo.set_call_status(session, call.id, CallStatus.FAILED, str(exc)[:500])
            result.failed_stages.append(StageKey.TRANSCRIBE.value)
            return result

        # -- One script -------------------------------------------------
        # Before anything measures it. Deepgram returns Nastaliq for Urdu and
        # Devanagari for `multi`, and neither is what this product shows --
        # nor, in the Devanagari case, what the metrics engine can read: it
        # detects that as English and applies English pace benchmarks.
        if get_settings().transcript_script == "roman":
            try:
                asr.sentences, changed = await romanise(self.providers, asr.sentences)
                if changed:
                    log.info("romanised the transcript for %s", call.id)
            except Exception:  # noqa: BLE001
                # Never fatal. The original script measures correctly; it is
                # only inconsistent with the rest of the interface.
                log.exception("romanising failed for %s; keeping the original", call.id)

        await bus.emit(
            call.id, StageKey.TRANSCRIBE, StageStatus.OK,
            detail=f"{len(asr.sentences)} utterances",
            progress=0.2, elapsed_ms=elapsed(),
        )

        # -- Speaker roles ----------------------------------------------
        await bus.emit(call.id, StageKey.DIARIZE, StageStatus.RUNNING, progress=0.25)
        transcript = await self.transcriptionist.run(
            asr, call.id, rep_speaker_id=rep_speaker_id
        )
        result.transcript = transcript

        speakers = len({s.speaker_id for s in transcript.segments})
        await repo.put_artifact(session, call.id, repo.TRANSCRIPT, transcript)
        await bus.emit(
            call.id, StageKey.DIARIZE, StageStatus.OK,
            detail=f"{speakers} speakers separated",
            progress=0.32, elapsed_ms=elapsed(),
        )

        # -- Deterministic metrics --------------------------------------
        await bus.emit(call.id, StageKey.METRICS, StageStatus.RUNNING, progress=0.36)
        metrics = self.prosodist.run(transcript, asr.duration_ms or call.duration_ms)
        provisional = self.prosodist.score(metrics)
        result.metrics, result.scorecard = metrics, provisional

        call.duration_ms = metrics.duration_ms
        await repo.put_artifact(session, call.id, repo.METRICS, metrics)
        await repo.put_artifact(session, call.id, repo.SCORECARD, provisional)
        await repo.put_call(session, call, score=provisional.overall)
        await bus.emit(
            call.id, StageKey.METRICS, StageStatus.OK,
            detail=(
                f"talk ratio {round(metrics.talk_ratio_rep * 100)}%, "
                f"longest monologue {metrics.longest_monologue_ms // 1000}s"
            ),
            progress=0.45, elapsed_ms=elapsed(),
            payload={
                "talk_ratio_rep": metrics.talk_ratio_rep,
                "longest_monologue_ms": metrics.longest_monologue_ms,
                "patience_ms": metrics.patience_ms,
            },
        )

        # -- Call anatomy (degrades) ------------------------------------
        await bus.emit(call.id, StageKey.ANATOMY, StageStatus.RUNNING, progress=0.5)
        analysis: Optional[CallAnalysis] = None
        try:
            analysis = await self.anatomist.run(
                transcript, call.id, metrics=metrics, context=deal_context
            )
            result.analysis = analysis
            await repo.put_artifact(session, call.id, repo.ANALYSIS, analysis)
            await bus.emit(
                call.id, StageKey.ANATOMY, StageStatus.OK,
                detail=(
                    f"{len(analysis.objections)} objection(s), "
                    f"MEDDIC {round(analysis.meddic.coverage_ratio() * 100)}%"
                ),
                progress=0.68, elapsed_ms=elapsed(),
                payload={"citation_coverage": citation_coverage(analysis)},
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("anatomy failed for %s", call.id)
            result.failed_stages.append(StageKey.ANATOMY.value)
            await bus.emit(
                call.id, StageKey.ANATOMY, StageStatus.FAILED,
                detail=str(exc)[:200], elapsed_ms=elapsed(),
            )

        # -- Plays and the moment index (degrades) ----------------------
        if analysis is not None:
            await bus.emit(call.id, StageKey.PLAYS, StageStatus.RUNNING, progress=0.72)
            try:
                plays = await self.playwright.run(
                    session, call, transcript, analysis, rep_name=rep_name
                )
                result.plays = plays
                await bus.emit(
                    call.id, StageKey.PLAYS, StageStatus.OK,
                    detail=(
                        f"{len(plays)} play(s): "
                        + ", ".join(p.name for p in plays[:3])
                        if plays
                        else "no reusable plays in this call"
                    ),
                    progress=0.85, elapsed_ms=elapsed(),
                    payload={"plays": [{"id": p.id, "name": p.name} for p in plays]},
                )
                await bus.emit(
                    call.id, StageKey.EMBED, StageStatus.OK,
                    detail="moments indexed for retrieval",
                    progress=0.88, elapsed_ms=elapsed(),
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("play extraction failed for %s", call.id)
                result.failed_stages.append(StageKey.PLAYS.value)
                await bus.emit(
                    call.id, StageKey.PLAYS, StageStatus.FAILED,
                    detail=str(exc)[:200], elapsed_ms=elapsed(),
                )
        else:
            await bus.emit(
                call.id, StageKey.PLAYS, StageStatus.SKIPPED,
                detail="needs call anatomy", progress=0.85,
            )
            await bus.emit(call.id, StageKey.EMBED, StageStatus.SKIPPED, progress=0.88)

        # -- Final scorecard, now that interpretation exists -------------
        final = self.prosodist.score(metrics, analysis, plays_landed=len(result.plays))
        result.scorecard = final
        await repo.put_artifact(session, call.id, repo.SCORECARD, final)
        await repo.put_call(session, call, score=final.overall)

        # -- Deal trajectory (degrades) ---------------------------------
        if call.deal_id:
            await bus.emit(call.id, StageKey.TRAJECTORY, StageStatus.RUNNING, progress=0.92)
            try:
                deal = await repo.get_deal(session, call.deal_id)
                if deal is not None:
                    trajectory = await self.analyst.trajectory(session, deal, rep_name)
                    await bus.emit(
                        call.id, StageKey.TRAJECTORY, StageStatus.OK,
                        detail=trajectory.verdict,
                        progress=0.97, elapsed_ms=elapsed(),
                        payload={
                            "health": trajectory.health,
                            "risks": len(trajectory.risks),
                        },
                    )
            except Exception as exc:  # noqa: BLE001
                log.exception("trajectory failed for %s", call.id)
                result.failed_stages.append(StageKey.TRAJECTORY.value)
                await bus.emit(
                    call.id, StageKey.TRAJECTORY, StageStatus.FAILED,
                    detail=str(exc)[:200],
                )
        else:
            await bus.emit(
                call.id, StageKey.TRAJECTORY, StageStatus.SKIPPED,
                detail="call is not attached to a deal", progress=0.97,
            )

        await repo.set_call_status(session, call.id, CallStatus.READY)
        result.elapsed_ms = elapsed()

        await bus.emit(
            call.id, StageKey.DONE, StageStatus.OK,
            detail=f"score {final.overall}",
            progress=1.0, elapsed_ms=result.elapsed_ms,
            payload={
                "score": final.overall,
                "failed_stages": result.failed_stages,
            },
        )
        log.info(
            "pipeline complete for %s in %dms (%d stage failure(s))",
            call.id, result.elapsed_ms, len(result.failed_stages),
        )
        return result


async def run_in_background(
    providers: Providers,
    call: Call,
    *,
    audio_url: Optional[str] = None,
    rep_speaker_id: Optional[int] = None,
    rep_name: str = "",
    language: str = "",
) -> None:
    """Entry point for the upload endpoint.

    Opens its own session because the request that started it has already
    returned, and swallows everything: an unhandled exception in a background
    task would otherwise vanish into the event loop with the browser still
    waiting on the SSE stream.
    """
    pipeline = Pipeline(providers)
    try:
        async with session_scope() as session:
            await pipeline.run(
                session,
                call,
                audio_url=audio_url,
                rep_speaker_id=rep_speaker_id,
                rep_name=rep_name,
                language=language,
            )
    except Exception as exc:  # noqa: BLE001
        log.exception("background pipeline crashed for %s", call.id)
        await bus.emit(
            call.id, StageKey.DONE, StageStatus.FAILED, detail=str(exc)[:300]
        )
        try:
            async with session_scope() as session:
                await repo.set_call_status(
                    session, call.id, CallStatus.FAILED, str(exc)[:500]
                )
        except Exception:  # noqa: BLE001
            log.exception("could not record failure status for %s", call.id)


async def run_batch(
    providers: Providers,
    calls: list[tuple[Call, str, str]],
    *,
    concurrency: int = 3,
) -> list[PipelineResult]:
    """Analyse many calls at once, bounded.

    This is where the real parallelism lives: a single call is inherently
    sequential (you cannot read anatomy before you have a transcript), but a
    seed corpus of a dozen calls fans out cleanly. Concurrency is capped
    because the provider rate limits are the actual constraint, not the CPU.
    """
    pipeline = Pipeline(providers)
    gate = asyncio.Semaphore(concurrency)

    async def one(call: Call, audio_url: str, rep_name: str) -> PipelineResult:
        async with gate:
            async with session_scope() as session:
                return await pipeline.run(
                    session, call, audio_url=audio_url, rep_name=rep_name
                )

    settled = await asyncio.gather(
        *(one(c, url, name) for c, url, name in calls), return_exceptions=True
    )

    results: list[PipelineResult] = []
    for item, (call, _, _) in zip(settled, calls):
        if isinstance(item, BaseException):
            log.error("batch item %s failed: %s", call.id, item)
            results.append(PipelineResult(call=call, failed_stages=["batch"]))
        else:
            results.append(item)
    return results
