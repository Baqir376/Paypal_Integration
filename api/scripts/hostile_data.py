# -*- coding: utf-8 -*-
"""Write calls into the database that a demo would rather not meet.

Every screen in this product renders artefacts produced by a seven-stage
pipeline where each stage is allowed to fail on its own. That is a deliberate
design -- a failed play extraction should not cost you the transcript -- and it
means the interface must render every partial combination those failures
produce. A call with a transcript and no analysis. A scorecard with no
transcript. A call that failed at stage one and has nothing at all.

Nothing in the test suite covers that, because the tests exercise the API and
the API is happy to return `null`. The crash happens later, in a component that
assumed a field was there, in front of whoever is watching the demo.

    cd api
    .venv/Scripts/python -m scripts.hostile_data          # write them
    .venv/Scripts/python -m scripts.hostile_data --clean  # remove them

Then drive the browser at them: `node scripts/crash_hunt.mjs` in web/.

Every call written here is prefixed `hostile_` so `--clean` can find them and
nothing else is touched.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "api"))

from salix.schemas.analysis import (  # noqa: E402
    CallAnalysis,
    MeddicCoverage,
    MeddicItem,
)
from salix.schemas.common import EvidenceRef  # noqa: E402
from salix.schemas.call import Call, CallStatus, Segment, Transcript  # noqa: E402
from salix.schemas.common import CallOutcome, SpeakerRole  # noqa: E402
from salix.schemas.metrics import CallMetrics  # noqa: E402
from salix.store import repo  # noqa: E402
from salix.store.db import session_scope  # noqa: E402

PREFIX = "hostile_"


def _call(suffix: str, title: str, org: str, rep: str, status=CallStatus.READY) -> Call:
    return Call(
        id=f"{PREFIX}{suffix}",
        org_id=org,
        rep_id=rep,
        title=title,
        account="Hostile QA",
        occurred_at=datetime.now(timezone.utc),
        status=status,
        outcome=CallOutcome.OPEN,
    )


def _segment(index: int, role: SpeakerRole, start: int, end: int, text: str) -> Segment:
    return Segment(
        id=f"seg_{index}", index=index,
        speaker_id=0 if role is SpeakerRole.REP else 1,
        role=role, start_ms=start, end_ms=end, text=text,
    )


async def write() -> int:
    async with session_scope() as session:
        org = await repo.first_org(session)
        if org is None:
            print("  no organisation. Run seed.blank first.")
            return 1
        reps = await repo.list_reps(session, org.id)
        if not reps:
            print("  no reps. Run seed.blank first.")
            return 1
        rep = reps[0].id

        # 1. Failed at the first stage. No transcript, no metrics, no anything.
        #    This is what a real upload of a silent file leaves behind.
        call = _call("failed", "Failed at transcription", org.id, rep, CallStatus.FAILED)
        call.error = "Transcription failed: no speech detected."
        await repo.put_call(session, call)

        # 2. Still running. The page is reached by someone who bookmarked it.
        await repo.put_call(session, _call(
            "running", "Still transcribing", org.id, rep, CallStatus.TRANSCRIBING))

        # 3. Transcript, and nothing else. Anatomy and plays both failed.
        call = _call("nometrics", "Transcript only, no analysis", org.id, rep)
        await repo.put_call(session, call)
        await repo.put_artifact(session, call.id, repo.TRANSCRIPT, Transcript(
            call_id=call.id,
            segments=[
                _segment(0, SpeakerRole.REP, 0, 4000, "Thanks for the time today."),
                _segment(1, SpeakerRole.BUYER, 4500, 9000, "It is manual, mostly."),
            ],
        ))

        # 4. Metrics with no transcript. The scorecard renders, the citations
        #    it wants to resolve point at nothing.
        call = _call("notranscript", "Metrics with no transcript", org.id, rep)
        await repo.put_call(session, call)
        await repo.put_artifact(session, call.id, repo.METRICS, CallMetrics(
            call_id=call.id, duration_ms=600_000, rep_talk_ms=300_000,
            buyer_talk_ms=300_000, talk_ratio_rep=0.5,
        ))

        # 5. One segment, zero length, no words. Every per-minute rate divides
        #    by a duration of zero.
        call = _call("empty", "One empty segment", org.id, rep)
        await repo.put_call(session, call)
        await repo.put_artifact(session, call.id, repo.TRANSCRIPT, Transcript(
            call_id=call.id,
            segments=[_segment(0, SpeakerRole.REP, 0, 0, "")],
        ))

        # 6. Analysis whose citations name segments that do not exist. The
        #    pipeline drops these, but a hand-written artefact or an older
        #    record can carry them, and the call page hydrates citations.
        call = _call("badcites", "Analysis citing missing segments", org.id, rep)
        await repo.put_call(session, call)
        await repo.put_artifact(session, call.id, repo.TRANSCRIPT, Transcript(
            call_id=call.id,
            segments=[_segment(0, SpeakerRole.REP, 0, 5000, "Only one line exists.")],
        ))
        missing = [
            EvidenceRef(segment_id="seg_404", quote="a line that was never said"),
            EvidenceRef(segment_id="seg_999", quote="nor was this one"),
        ]
        empty = MeddicItem(covered=False)
        await repo.put_artifact(session, call.id, repo.ANALYSIS, CallAnalysis(
            call_id=call.id,
            summary="Every citation in this analysis names a segment that is absent.",
            headline="Every citation below points at a segment that is not there.",
            meddic=MeddicCoverage(
                metrics=MeddicItem(covered=True, confidence=0.9, evidence=missing),
                economic_buyer=empty,
                decision_criteria=empty,
                decision_process=empty,
                identify_pain=MeddicItem(covered=True, confidence=0.8, evidence=missing),
                champion=empty,
            ),
        ))

        # 7. Text that has broken a renderer somewhere before: markup, an
        #    unclosed tag, an emoji, a very long unbroken token.
        call = _call("nasty", "Nasty text in the transcript", org.id, rep)
        await repo.put_call(session, call)
        await repo.put_artifact(session, call.id, repo.TRANSCRIPT, Transcript(
            call_id=call.id,
            segments=[
                _segment(0, SpeakerRole.REP, 0, 3000,
                         "<script>alert('x')</script> & <b>unclosed"),
                _segment(1, SpeakerRole.BUYER, 3200, 6000, "😡" * 40),
                _segment(2, SpeakerRole.REP, 6200, 9000, "A" * 900),
                _segment(3, SpeakerRole.BUYER, 9200, 12000,
                         "آپ کی قیمت زیادہ ہے۔ Aur yeh Roman bhi hai. 混合"),
            ],
        ))

        # 8. Numbers at the edges of what the interface formats.
        call = _call("extremes", "Extreme measurements", org.id, rep)
        await repo.put_call(session, call)
        await repo.put_artifact(session, call.id, repo.METRICS, CallMetrics(
            call_id=call.id,
            duration_ms=86_400_000,          # a twenty-four hour call
            rep_talk_ms=86_400_000,
            buyer_talk_ms=0,
            talk_ratio_rep=1.0,              # nobody else spoke
            longest_monologue_ms=86_400_000,
            patience_ms=0.0,
            rep_wpm=0.0,
            rep_question_count=0,
        ))

        await session.commit()

    print(f"  wrote 8 hostile calls, all prefixed `{PREFIX}`")
    return 0


async def clean() -> int:
    from sqlalchemy import delete

    from salix.store.models import ArtifactRow, CallRow

    async with session_scope() as session:
        await session.execute(delete(ArtifactRow).where(ArtifactRow.call_id.startswith(PREFIX)))
        await session.execute(delete(CallRow).where(CallRow.id.startswith(PREFIX)))
        await session.commit()
    print("  removed every hostile call")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    return await (clean() if args.clean else write())


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
