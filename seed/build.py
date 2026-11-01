"""Build the seed database.

Runs the ten seed conversations through the *real* pipeline -- the same DAG an
uploaded recording goes through -- so the demo shows genuine analysis of genuine
transcripts rather than hand-written fixtures.

    python -m seed.build              # analyse, offline or live per env
    python -m seed.build --reset      # drop and rebuild from scratch
    python -m seed.build --audio      # also synthesize MP3s with Qwen TTS
    python -m seed.build --report     # generate the cycle report at the end

With no API key it runs on the offline providers and still populates every
screen. With `DASHSCOPE_API_KEY` set it uses Qwen for anatomy, plays, coaching
and the report, and `--audio` produces real two-speaker recordings.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "api") not in sys.path:
    sys.path.insert(0, str(REPO / "api"))

from sqlalchemy import delete  # noqa: E402

from salix.agents.analyst import Analyst  # noqa: E402
from salix.agents.coach import Coach  # noqa: E402
from salix.config import get_settings  # noqa: E402
from salix.pipeline.orchestrator import Pipeline  # noqa: E402
from salix.providers import build_providers  # noqa: E402
from salix.providers.mock import MockASR  # noqa: E402
from salix.schemas.call import Call, CallStatus  # noqa: E402
from salix.schemas.common import CallOutcome, DealStage  # noqa: E402
from salix.schemas.deal import Deal  # noqa: E402
from salix.schemas.org import Org, Rep  # noqa: E402
from salix.store import db, repo, session_scope  # noqa: E402
from salix.store.models import OrgRow  # noqa: E402

from . import cast, scripts  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)-24s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seed")


class ScriptedASR:
    """Feeds a seed script into the pipeline.

    When real audio exists for a call and we are running live, the genuine ASR
    provider is used instead -- the point of the seed corpus is to exercise the
    real path, not to bypass it.
    """

    name = "scripted"

    def __init__(self, script_by_call: dict[str, str], live_asr=None, audio_dir=None):
        self.script_by_call = script_by_call
        self.live_asr = live_asr
        self.audio_dir = audio_dir
        self.current_call_id: str | None = None

    async def transcribe(self, audio_url: str, *, diarize=True, language_hints=("en",)):
        if self.live_asr is not None and audio_url.startswith(("http://", "https://")):
            return await self.live_asr.transcribe(
                audio_url, diarize=diarize, language_hints=language_hints
            )
        script = self.script_by_call[self.current_call_id or ""]
        return MockASR.from_script(script)


async def reset_database() -> None:
    log.info("dropping existing schema")
    await db.drop_all()
    await db.init_db()


async def load_entities() -> None:
    """Write the org, people and deals. Idempotent."""
    async with session_scope() as session:
        # Started the API first? It made an empty default org, and `first_org`
        # has to find this one instead.
        await session.execute(delete(OrgRow).where(OrgRow.id == repo.DEFAULT_ORG_ID))
        await repo.put_org(session, Org(**cast.ORG))

        for raw in cast.REPS:
            await repo.put_rep(
                session,
                Rep(
                    id=raw["id"], org_id=cast.ORG_ID, name=raw["name"],
                    role=raw["role"], initials=raw["initials"], quota=raw["quota"],
                    attained=raw["attained"], joined_at=raw["joined_at"],
                    is_top_performer=raw["is_top_performer"],
                ),
            )

        for raw in cast.DEALS:
            await repo.put_deal(
                session,
                Deal(
                    id=raw["id"], org_id=cast.ORG_ID, name=raw["name"],
                    account=raw["account"], owner_id=raw["owner_id"],
                    value=raw["value"], stage=DealStage(raw["stage"]),
                    outcome=CallOutcome(raw["outcome"]),
                    opened_at=datetime.fromisoformat(raw["opened_at"]),
                    closed_at=(
                        datetime.fromisoformat(raw["closed_at"])
                        if raw["closed_at"] else None
                    ),
                    contacts=raw["contacts"],
                ),
            )

    log.info(
        "loaded %d reps and %d deals for %s",
        len(cast.REPS), len(cast.DEALS), cast.ORG["name"],
    )


async def synthesize_audio(providers, settings) -> dict[str, str]:
    """Render each script to a two-voice MP3 with Qwen TTS.

    Each speaker gets a distinct voice so that speaker diarization has a real
    signal to separate, and the concatenated result is a genuine recording that
    the live ASR path can transcribe.
    """
    try:
        from pydub import AudioSegment  # type: ignore
    except ImportError:
        log.warning(
            "audio synthesis needs pydub and ffmpeg; skipping (pip install pydub)"
        )
        return {}

    out_dir = settings.audio_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    produced: dict[str, str] = {}

    for meta in cast.CALLS:
        target = out_dir / f"{meta['id']}.mp3"
        if target.exists():
            log.info("audio already present for %s", meta["id"])
            produced[meta["id"]] = str(target)
            continue

        rep_voice = cast.rep_for(meta["rep_id"])["voice"]
        buyer_voice = cast.deal_for(meta["deal_id"])["buyer_voice"]
        script = scripts.get(meta["script"])

        track = AudioSegment.silent(duration=600)
        log.info("synthesizing %s", meta["id"])

        for line in script.splitlines():
            if not line.strip() or ":" not in line:
                continue
            speaker, text = line.split(":", 1)
            is_rep = speaker.strip().upper().startswith("REP")
            try:
                audio = await providers.tts.synthesize(
                    text.strip(),
                    voice=rep_voice if is_rep else buyer_voice,
                    instruction=(
                        "Speak naturally, as on a business phone call."
                        if is_rep
                        else "Speak naturally, slightly guarded, as a prospective buyer."
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                log.error("TTS failed on a line of %s: %s", meta["id"], exc)
                return produced

            import io

            track += AudioSegment.from_file(io.BytesIO(audio))
            track += AudioSegment.silent(duration=450)

        # Diarization on Model Studio requires mono.
        track.set_channels(1).export(target, format="mp3")
        produced[meta["id"]] = str(target)
        log.info("wrote %s (%.1fs)", target.name, len(track) / 1000)

    return produced


async def analyze(providers, audio_by_call: dict[str, str]) -> None:
    """Run every seed call through the pipeline."""
    script_by_call = {m["id"]: scripts.get(m["script"]) for m in cast.CALLS}
    asr = ScriptedASR(script_by_call, live_asr=providers.asr)
    providers.asr = asr

    pipeline = Pipeline(providers)
    started = time.monotonic()

    for index, meta in enumerate(cast.CALLS, start=1):
        deal = cast.deal_for(meta["deal_id"])
        rep = cast.rep_for(meta["rep_id"])
        asr.current_call_id = meta["id"]

        call = Call(
            id=meta["id"],
            org_id=cast.ORG_ID,
            deal_id=meta["deal_id"],
            rep_id=meta["rep_id"],
            title=meta["title"],
            account=meta["account"],
            occurred_at=meta["occurred_at"],
            audio_url=audio_by_call.get(meta["id"]),
            status=CallStatus.UPLOADED,
            outcome=CallOutcome(meta["outcome"]),
        )

        log.info(
            "[%d/%d] %s -- %s", index, len(cast.CALLS), meta["id"], meta["title"]
        )
        async with session_scope() as session:
            await repo.put_call(session, call)
            result = await pipeline.run(
                session,
                call,
                audio_url=call.audio_url,
                rep_name=rep["name"],
                deal_context=(
                    f"Account: {deal['account']}. Deal value: {deal['value']:,}. "
                    f"Stage: {deal['stage']}. "
                    f"Known contacts: {', '.join(deal['contacts'])}."
                ),
            )

        if result.ok:
            log.info(
                "      score %.1f | talk %.0f%% | monologue %ds | %d play(s)%s",
                result.scorecard.overall,
                result.metrics.talk_ratio_rep * 100,
                result.metrics.longest_monologue_ms // 1000,
                len(result.plays),
                f" | FAILED: {result.failed_stages}" if result.failed_stages else "",
            )
        else:
            log.error("      failed: %s", result.failed_stages)

    log.info("analysed %d calls in %.1fs", len(cast.CALLS), time.monotonic() - started)


async def coach_the_team(providers) -> None:
    """Generate a coaching plan for everyone below the team ceiling."""
    coach = Coach(providers)
    async with session_scope() as session:
        reps = await repo.list_reps(session, cast.ORG_ID)
        for rep in reps:
            if rep.is_top_performer:
                continue
            plan = await coach.run(session, cast.ORG_ID, rep)
            log.info(
                "coaching plan for %s: %d gap(s), %s",
                rep.name,
                len(plan.gaps),
                "script generated" if plan.script else "no script",
            )


async def build_report(providers) -> None:
    analyst = Analyst(providers)
    async with session_scope() as session:
        report = await analyst.cycle_report(session, cast.ORG_ID, cast.ORG["cycle_label"])
    log.info("cycle report: %s", report.headline)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Salix seed database")
    parser.add_argument("--reset", action="store_true", help="drop and recreate schema")
    parser.add_argument("--audio", action="store_true", help="synthesize MP3s via TTS")
    parser.add_argument("--no-coach", action="store_true", help="skip coaching plans")
    parser.add_argument("--report", action="store_true", help="generate cycle report")
    parser.add_argument("--all", action="store_true", help="reset, coach and report")
    args = parser.parse_args()

    if args.all:
        args.reset = args.report = True

    settings = get_settings()
    providers = build_providers(settings)
    log.info(
        "provider mode: %s%s",
        providers.mode.upper(),
        f" ({settings.model_deep})" if providers.mode == "live" else "",
    )

    await db.init_db()
    if args.reset:
        await reset_database()

    await load_entities()

    audio: dict[str, str] = {}
    if args.audio:
        if providers.mode != "live":
            log.warning("--audio needs a DASHSCOPE_API_KEY; skipping synthesis")
        else:
            audio = await synthesize_audio(providers, settings)

    await analyze(providers, audio)

    if not args.no_coach:
        await coach_the_team(providers)
    if args.report:
        await build_report(providers)

    async with session_scope() as session:
        plays = await repo.list_plays(session, cast.ORG_ID)
        moments = await repo.count_moments(session, cast.ORG_ID)

    log.info("-" * 62)
    log.info("Seed complete.")
    log.info("  playbook : %d play(s)", len(plays))
    for play in sorted(plays, key=lambda p: -p.usage_count)[:8]:
        log.info("             %-32s used %dx", play.name, play.usage_count)
    log.info("  moments  : %d indexed for retrieval", moments)
    log.info("  database : %s", settings.database_url)
    await db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
