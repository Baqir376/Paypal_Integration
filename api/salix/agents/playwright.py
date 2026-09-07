"""Playwright -- mines winning calls for reusable narrative moves.

This is the heart of the product. Anyone can tell a struggling rep to talk
less. What actually moves a number is showing them the specific narrative move
a teammate used to turn the same objection, in that teammate's own words, with
the recording to back it up.

Two jobs:

1. **Extraction.** Find the moments where the rep did something structurally
   reusable -- told a story, reached for an analogy, reframed a problem,
   deployed a proof point -- and describe it as a play someone else could run.

2. **Convergence.** A team of five reps generates hundreds of candidates that
   are mostly the same handful of moves rediscovered. New candidates are
   embedded and compared against the library; a near-match becomes another
   instance of the existing play rather than a near-duplicate entry. That is
   what makes the playbook converge on a dozen named moves instead of sprawling
   into an unusable list.

It also writes the moment index that the Coach later retrieves from.
"""

from __future__ import annotations

import logging
import uuid

from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.analysis import CallAnalysis
from ..schemas.call import Call, Transcript
from ..schemas.common import CallOutcome, SalixModel, SpeakerRole
from ..schemas.play import Play, PlayCandidate, PlayInstance
from ..store import repo
from .base import Agent

log = logging.getLogger("salix.playwright")

# Cosine similarity above which a candidate is the same play as an existing
# one. Tuned on the seed corpus: 0.82 merges genuine restatements while
# keeping "The Compounding Cost" and "The Silent Renewal" apart.
DEDUP_THRESHOLD = 0.82

# Moment kinds in the retrieval index.
KIND_PLAY = "play"
KIND_OBJECTION = "objection_handling"
KIND_DISCOVERY = "discovery"
KIND_CLOSE = "close"


ROLE = """\
Your job is to find the reusable narrative moves a salesperson made on this
call -- the things that would still work if a different rep said them to a
different buyer next week.

WHAT COUNTS AS A PLAY

A play is a structural move, not a sentence. Look for:
- story_arc: a narrative about another customer, with a before, a turn, an after
- analogy: an unfamiliar thing explained through a familiar one
- proof_point: a specific, checkable fact deployed at the moment of doubt
- reframe: changing what the buyer thinks the decision is actually about
- question_sequence: two or more questions that build deliberately toward a
  realisation the buyer reaches themselves
- objection_turn: an objection converted into a reason to move forward

WHAT DOES NOT COUNT
Ordinary competence is not a play. Being polite, summarising, confirming a
time, listing features, saying "great question" -- none of these are moves.
If the call contains no genuine plays, return an empty list. That is a normal
and useful answer.

FOR EACH PLAY
- `name`: short, memorable, title-cased, describing the move rather than the
  customer. "The Compounding Cost" is a good name. "Acme Story" is not.
- `thesis`: one sentence on what the move does to a buyer psychologically.
- `when_to_use`: the situation that should trigger it.
- `beats`: the structural steps in order, so someone else can run it.
- `template`: how to say it, with [BRACKETED] slots for the parts that change.
- `quote`: the verbatim passage from the transcript where it lands.
- `segment_ids`: the lines it spans. Required, and they must be real.
- `effectiveness`: judge from what the buyer said next, not from how polished
  the rep sounded. A beautiful story that changed nothing scores low.
"""


class PlayHarvest(SalixModel):
    """Wrapper, because structured generation returns one object."""

    plays: list[PlayCandidate] = Field(default_factory=list)


class Playwright(Agent):
    name = "Playwright"

    async def run(
        self,
        session: AsyncSession,
        call: Call,
        transcript: Transcript,
        analysis: CallAnalysis,
        rep_name: str = "",
    ) -> list[Play]:
        """Extract, merge into the library, and index the call's moments."""
        candidates = await self.extract(transcript, analysis, call)
        plays = await self.merge(session, call, candidates, rep_name)
        await self.index_moments(session, call, transcript, analysis, plays)
        return plays

    # -- extraction ------------------------------------------------------

    async def extract(
        self, transcript: Transcript, analysis: CallAnalysis, call: Call
    ) -> list[PlayCandidate]:
        context = [
            f"Call outcome: {call.outcome.value}",
            f"Account: {call.account}",
            f"What decided the call: {analysis.headline}",
        ]
        if analysis.objections:
            context.append(
                "Objections raised: "
                + "; ".join(f"{o.category.value} -- {o.text}" for o in analysis.objections)
            )

        harvest = await self.grounded(
            system=self.system_prompt(ROLE),
            user="\n".join(context) + f"\n\nTRANSCRIPT\n{transcript.render()}",
            schema=PlayHarvest,
            transcript=transcript,
            call_id=call.id,
            # Naming a play does benefit from a little room. A play
            # appearing on one run and vanishing on the next does not, and
            # that is what the room was buying.
            temperature=0.0,
            max_tokens=8000,
        )

        # Candidates cite segment ids directly rather than through EvidenceRef,
        # so they are validated here instead of by the shared hydration pass.
        valid_ids = {s.id for s in transcript.segments}
        kept: list[PlayCandidate] = []
        for candidate in harvest.plays:
            real = [sid for sid in candidate.segment_ids if sid in valid_ids]
            if not real:
                log.warning(
                    "dropping play %r: no valid segment ids in %s",
                    candidate.name, candidate.segment_ids[:5],
                )
                continue
            candidate.segment_ids = real
            kept.append(candidate)

        log.info("extracted %d play(s) from %s", len(kept), call.id)
        return kept

    # -- convergence -----------------------------------------------------

    async def merge(
        self,
        session: AsyncSession,
        call: Call,
        candidates: list[PlayCandidate],
        rep_name: str = "",
    ) -> list[Play]:
        """Fold candidates into the org playbook, deduplicating by meaning."""
        if not candidates:
            return []

        texts = [self._signature(c) for c in candidates]
        embeddings = await self.embeddings.embed(texts)
        merged: list[Play] = []

        for candidate, embedding in zip(candidates, embeddings):
            existing = await repo.nearest_play(
                session, call.org_id, embedding, DEDUP_THRESHOLD
            )

            if existing is not None:
                play, score = existing
                log.info(
                    "play %r merged into existing %r (similarity %.2f)",
                    candidate.name, play.name, score,
                )
            else:
                play = Play(
                    id=f"play_{uuid.uuid4().hex[:10]}",
                    org_id=call.org_id,
                    name=candidate.name,
                    kind=candidate.kind,
                    thesis=candidate.thesis,
                    when_to_use=candidate.when_to_use,
                    beats=candidate.beats,
                    template=candidate.template,
                    origin_rep_id=call.rep_id,
                    origin_rep_name=rep_name,
                )

            instance = PlayInstance(
                id=f"pi_{uuid.uuid4().hex[:10]}",
                play_id=play.id,
                call_id=call.id,
                rep_id=call.rep_id,
                rep_name=rep_name,
                account=call.account,
                outcome=call.outcome.value,
                quote=candidate.quote,
                evidence=[],
                effectiveness=candidate.effectiveness,
            )
            # Re-running a call must not inflate the counts.
            play.instances = [
                i for i in play.instances if i.call_id != call.id
            ] + [instance]
            play.usage_count = len(play.instances)
            self._recompute_win_rate(play)

            await repo.put_play(session, play, embedding=embedding)
            merged.append(play)

        return merged

    def _signature(self, candidate: PlayCandidate) -> str:
        """What gets embedded for dedup.

        Deliberately the *shape* of the move -- kind, thesis, trigger, beats --
        and not the quote. Two reps telling the same structural story about
        different customers should collide; the same words about the same
        customer arriving twice should not be the only thing that does.
        """
        return " | ".join(
            [candidate.kind.value, candidate.thesis, candidate.when_to_use]
            + candidate.beats
        )

    def _recompute_win_rate(self, play: Play) -> None:
        """Win rate among calls where this play was run.

        `win_rate_without` needs org-wide numbers and is filled in by the
        Analyst at cycle roll-up; here we can only honestly compute the "with"
        side, and only once there is enough data to mean anything.
        """
        decided = [i for i in play.instances if i.outcome in ("won", "lost")]
        if len(decided) < 2:
            play.win_rate_with = None
            return
        won = sum(1 for i in decided if i.outcome == CallOutcome.WON.value)
        play.win_rate_with = round(won / len(decided), 3)

    # -- retrieval index -------------------------------------------------

    async def index_moments(
        self,
        session: AsyncSession,
        call: Call,
        transcript: Transcript,
        analysis: CallAnalysis,
        plays: list[Play],
    ) -> int:
        """Write this call's retrievable moments into the vector index.

        Each moment carries enough denormalised context to be useful straight
        out of a search result, because the Coach needs to show a rep *who*
        said it and *what happened next*, not just the text.
        """
        moments: list[dict] = []

        for play in plays:
            instance = next((i for i in play.instances if i.call_id == call.id), None)
            if instance is None:
                continue
            moments.append(
                self._moment(
                    call,
                    key=f"{call.id}:play:{play.id}",
                    kind=KIND_PLAY,
                    text=f"{play.name}. {play.thesis} {instance.quote}",
                    data={
                        "play_id": play.id,
                        "play_name": play.name,
                        "quote": instance.quote,
                        "account": call.account,
                        "effectiveness": instance.effectiveness,
                    },
                )
            )

        for objection in analysis.objections:
            if not objection.handled or objection.handling_quality < 3:
                continue
            response = " ".join(e.quote for e in objection.handling if e.quote)
            if not response:
                continue
            moments.append(
                self._moment(
                    call,
                    key=f"{call.id}:obj:{objection.id}",
                    kind=KIND_OBJECTION,
                    text=(
                        f"Objection ({objection.category.value}): {objection.text} "
                        f"Response: {response}"
                    ),
                    data={
                        "category": objection.category.value,
                        "objection": objection.text,
                        "quote": response,
                        "quality": objection.handling_quality,
                        "account": call.account,
                        "segment_id": objection.raised.segment_id,
                    },
                )
            )

        questions = [
            s for s in transcript.segments
            if s.role is SpeakerRole.REP and s.text.strip().endswith("?")
        ][:6]
        if questions:
            moments.append(
                self._moment(
                    call,
                    key=f"{call.id}:discovery",
                    kind=KIND_DISCOVERY,
                    text=" ".join(q.text for q in questions),
                    data={
                        "account": call.account,
                        "segment_ids": [q.id for q in questions],
                    },
                )
            )

        if analysis.next_step and analysis.next_step.evidence:
            moments.append(
                self._moment(
                    call,
                    key=f"{call.id}:close",
                    kind=KIND_CLOSE,
                    text=analysis.next_step.evidence.quote or analysis.next_step.text,
                    data={
                        "is_mutual": analysis.next_step.is_mutual,
                        "has_date": analysis.next_step.has_date,
                        "account": call.account,
                    },
                )
            )

        if not moments:
            return 0

        embeddings = await self.embeddings.embed([m["text"] for m in moments])
        for moment, embedding in zip(moments, embeddings):
            moment["embedding"] = embedding

        await repo.add_moments(session, moments)
        log.info("indexed %d moment(s) for %s", len(moments), call.id)
        return len(moments)

    def _moment(self, call: Call, *, key: str, kind: str, text: str, data: dict) -> dict:
        return {
            "id": key,
            "org_id": call.org_id,
            "call_id": call.id,
            "rep_id": call.rep_id,
            "kind": kind,
            "outcome": call.outcome.value,
            "text": text,
            "data": data,
        }
