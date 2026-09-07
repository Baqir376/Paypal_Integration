"""Deterministic offline stand-ins for every provider.

These exist so that a fresh clone with no API key still runs the entire system
end to end -- the pipeline, the DAG, the UI, the tests. They are seeded from
the input text, so the same input always yields the same output and the demo
never shifts underfoot.

`MockLLM.structured()` is the interesting one. Rather than hand-writing a fake
for every schema, it walks the Pydantic model and constructs a valid instance,
respecting enums, numeric bounds and required list lengths. That means a new
schema can never break mock mode. Where a realistic answer matters more than a
valid one -- call analysis, play extraction -- it reads the actual transcript
and produces something a person would recognise.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import re
from typing import Any, AsyncIterator, Optional, Sequence, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from .base import ASRResult, ASRSentence

# --------------------------------------------------------------------------
# Generic schema synthesis
# --------------------------------------------------------------------------

log = logging.getLogger("salix.providers.mock")

_PLACEHOLDER = "Generated in offline mode -- connect a Qwen API key for real analysis."


def _numeric_bounds(field: FieldInfo) -> tuple[float | None, float | None]:
    low = high = None
    for meta in field.metadata:
        for attr, target in (("ge", "low"), ("gt", "low"), ("le", "high"), ("lt", "high")):
            if hasattr(meta, attr):
                value = float(getattr(meta, attr))
                if target == "low":
                    low = value
                else:
                    high = value
    return low, high


def _min_length(field: FieldInfo) -> int:
    for meta in field.metadata:
        if hasattr(meta, "min_length"):
            return int(meta.min_length)
    return 0


def synthesize(model: type[BaseModel], rng: random.Random, depth: int = 0) -> Any:
    """Build a schema-valid instance of `model`. Never raises for a well-formed
    Pydantic model, which is the whole point."""
    values: dict[str, Any] = {}

    for name, field in model.model_fields.items():
        # A field can be optional yet still constrained -- `list = Field(
        # default_factory=list, min_length=1)` defaults to an empty list that
        # its own validator rejects. Those must be synthesized too.
        if not field.is_required() and _min_length(field) == 0:
            continue
        values[name] = _synthesize_value(
            field.annotation, field, rng, depth, hint=name
        )
    return model(**values)


def _synthesize_value(
    annotation: Any, field: FieldInfo, rng: random.Random, depth: int, hint: str = ""
) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)

    # Optional[X] -> None is always valid and cheapest.
    if origin is not None and type(None) in args:
        return None

    if origin in (list, Sequence):
        count = max(_min_length(field), 0)
        if not count or depth > 3:
            return []
        inner = args[0] if args else str
        return [
            _synthesize_value(inner, field, rng, depth + 1, hint) for _ in range(count)
        ]

    if origin is dict:
        return {}

    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel):
            if depth > 4:
                return None
            return synthesize(annotation, rng, depth + 1)
        if hasattr(annotation, "__members__"):  # Enum
            return list(annotation.__members__.values())[0]
        if annotation is bool:
            return False
        if annotation is int:
            low, high = _numeric_bounds(field)
            if low is not None and high is not None:
                return int((low + high) / 2)
            return int(low) if low is not None else 0
        if annotation is float:
            low, high = _numeric_bounds(field)
            if low is not None and high is not None:
                return round((low + high) / 2, 3)
            return float(low) if low is not None else 0.0
        if annotation is str:
            return _string_for(hint)

    return _string_for(hint)


def _string_for(hint: str) -> str:
    hint = hint.lower()
    if "id" in hint:
        return "s0000"
    if hint in {"quote", "text", "detail", "explanation", "note", "summary"}:
        return _PLACEHOLDER
    return _PLACEHOLDER


# --------------------------------------------------------------------------
# Transcript-aware heuristics
# --------------------------------------------------------------------------

# Phrase-shaped, not word-shaped. Bare words like "change", "cost" or "we use"
# appear constantly in ordinary buyer speech -- a clarifying question about
# pricing is not a pricing objection -- and matching them turns every call into
# a wall of false findings. Each cue below is a construction a buyer uses when
# they are actually pushing back.
OBJECTION_CUES: dict[str, tuple[str, ...]] = {
    "price": (
        "too expensive", "is expensive", "looks expensive", "beyond what we",
        "more than we were expecting", "cannot afford", "out of our budget",
        "price is high", "that price", "half of it for", "not a small decision",
        "is a lot for", "well beyond",
    ),
    "timing": (
        "next quarter", "not right now", "not the right time", "busiest period",
        "until the end of march", "no headcount", "hiring freeze",
        "guarantee it fails",
    ),
    "authority": (
        "my boss", "sign it off", "sign off", "would need approval",
        "goes to our", "controls the budget", "board asked", "my finance director",
        "would need to check with",
    ),
    "competition": (
        "we already use", "we currently use", "mostly works", "not unhappy",
        "does that too", "the other vendor", "incumbent",
    ),
    "status_quo": (
        "fine as is", "works well enough", "no appetite", "stay where we are",
        "not really a process", "nobody has ever", "would resist",
        "nothing catastrophic",
    ),
    "trust": (
        "how do we know", "would want proof", "i am sceptical", "i get sceptical",
        "sold to me", "bought two", "platform number three", "confidently told us",
    ),
    "risk": (
        "migration", "three years of history", "not searchable", "would evaporate",
        "data is clean enough", "run aground", "single point of failure",
        "if she left", "worries me",
    ),
    "fit": (
        "built for someone", "our size", "not sure it is aimed at us",
        "a hundred and eighty people", "we do not have a revenue operations team",
    ),
}

NEXT_STEP_CUES = (
    "next step", "follow up", "send you", "schedule", "calendar", "let us",
    "i will", "we will", "book", "meet again", "circle back", "monday",
    "tuesday", "wednesday", "thursday", "friday", "next week",
)

# The buyer agreeing is what makes a next step mutual rather than a promise the
# rep made to themselves.
AGREEMENT_CUES = (
    "that works", "works for me", "let us do that", "yes", "sounds good",
    "i will take it", "send it", "send them", "put something in", "book it",
    "that would be helpful", "i would like that", "we will find some time",
)

DATE_RE = re.compile(
    r"\b(mon|tues|wednes|thurs|fri)day\b|\bnext week\b"
    r"|\bthe (fourth|twelfth|eighteenth)\b|\bthis (afternoon|week)\b",
    re.IGNORECASE,
)

# Structural markers for the play kinds the Playwright looks for. Crude next to
# a language model, but they fire on the genuine article and stay quiet on
# ordinary competence, which is the property that matters.
PLAY_MARKERS: dict[str, tuple[str, ...]] = {
    "story_arc": (
        "can i tell you about", "one of our customers", "a team that",
        "a freight business", "a distribution business", "had almost exactly",
    ),
    "analogy": (
        "behaves much more like", "more like a", "think of it as",
        "wearing a", "is not really about",
    ),
    "reframe": (
        "compared to what", "the way i would frame it", "let me be careful",
        "the way i would put it", "part of what you are buying",
    ),
    "proof_point": (
        "went from", "measured it", "before and after", "percent inside",
    ),
    "objection_turn": (
        "and you should push back", "i would rather lose this",
        "i would rather hear", "i am not going to pretend",
    ),
}

PLAY_TITLES: dict[str, str] = {
    "story_arc": "The Compounding Cost",
    "analogy": "The Smoke Alarm",
    "reframe": "Compared To What",
    "proof_point": "The Measured Before And After",
    "objection_turn": "Naming The Risk First",
}

PLAY_THESES: dict[str, str] = {
    "story_arc": (
        "Shows the buyer their own problem happening to someone else, so the "
        "cost becomes concrete before any product is mentioned."
    ),
    "analogy": (
        "Replaces the buyer's mental model with a sharper one, so the flaw in "
        "their current process becomes self-evident."
    ),
    "reframe": (
        "Turns a price objection into a comparison the rep can actually win by "
        "making the buyer name their alternative."
    ),
    "proof_point": (
        "Anchors a claim to a measured before-and-after from a comparable "
        "customer, which survives scrutiny in a way an adjective does not."
    ),
    "objection_turn": (
        "Volunteers the weakness before the buyer finds it, which buys the "
        "credibility to be believed on everything else."
    ),
}


# A buyer line can mention price while agreeing. Without this guard the
# offline classifier reads "that is sensible, and it solves a problem for me"
# as a pricing objection, which then shows up as something the rep failed to
# handle -- and, worse, as an objection in their Dojo persona.
CONCESSION_CUES = (
    "that is sensible", "that is fair", "that is reasonable", "i like that",
    "that would be helpful", "good point", "that works", "i agree",
    "uncomfortably accurate", "annoyingly fair", "that is a good", "no argument",
    "you are right", "i will take it", "genuinely helpful", "that is more careful",
)


# Checked in this order, most specific first. Price cues are the most generic
# -- "budget" appears in plenty of lines whose real objection is something
# else -- so price is tested last. "My boss controls the budget" is an
# authority objection, not a pricing one, and coaching against the wrong
# category sends the rep to practise the wrong thing.
CATEGORY_PRECEDENCE = (
    "authority", "competition", "trust", "risk", "fit", "timing",
    "status_quo", "price",
)


def _classify_objection(text: str) -> Optional[str]:
    low = text.lower()
    if any(cue in low for cue in CONCESSION_CUES):
        return None
    for category in CATEGORY_PRECEDENCE:
        if any(cue in low for cue in OBJECTION_CUES.get(category, ())):
            return category
    return None


# Used when a real recording is uploaded with no API key configured. Failing
# the upload would leave a judge staring at a red stage on the ingest screen,
# so the DAG runs on this instead -- and the transcript says plainly what it
# is, so nobody mistakes it for a transcription of their own audio. Written as
# a mixed-quality call so the metrics engine has something to say about it.
STAND_IN_CALL = """\
REP: Thanks for making the time today. Before we start, this transcript is a stand-in and this conversation did not happen. No speech-to-text provider with speaker separation is configured, so the audio that was uploaded has been stored but never listened to. Everything after this point is the real pipeline running on this text instead.
BUYER: Understood. So walk me through what you would normally do with a recording like ours, because we have been burned by tools that promise a lot here.
REP: The audio goes to Qwen ASR with speaker diarization. We get back sentences with millisecond timestamps and a speaker label, and from there every number you see is arithmetic rather than a guess.
BUYER: What sort of numbers? We already have a dashboard that tells us how many calls people made and how long they were, and it has never once changed what anybody does on a Tuesday.
REP: Talk ratio against the forty three percent benchmark, longest unbroken stretch, how long the rep waits after the buyer stops speaking, how many questions were asked and how many of those were open-ended. Then a language model reads the structure on top of that.
BUYER: The structure part is where I get sceptical. We looked at two of these and both of them confidently told us things that were simply not said on the call. Once that happens you stop trusting any of it.
REP: That is the failure mode this is designed against. Every finding has to name the transcript line it came from. If it names a line that does not exist, it gets sent back with the list of lines that do, and if it still cannot point at a real one the claim is dropped rather than shown to you.
BUYER: That is more careful than what we saw. What does it cost to find out whether it works on our own calls?
REP: Configure a transcription provider that does diarization and this stand-in disappears. You would be looking at your own recordings within the hour. That is the honest answer to what it costs to evaluate.
BUYER: Alright. Send me what I need to set it up and I will look at it properly this week.
REP: I will put it in an email this afternoon.
"""


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------


class MockLLM:
    name = "mock"

    def __init__(self, settings=None):
        self.settings = settings

    def _rng(self, *parts: str) -> random.Random:
        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
        return random.Random(int(digest[:16], 16))

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        return _PLACEHOLDER

    async def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
        repair_attempts: int = 2,
    ) -> Any:
        rng = self._rng(schema.__name__, user[:400])

        builder = getattr(self, f"_build_{schema.__name__}", None)
        if builder is not None:
            built = builder(user, rng)
            if built is not None:
                return built
        return synthesize(schema, rng)

    async def stream(
        self,
        *,
        system: str,
        user: str,
        history: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.6,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        # A plausible buyer turn for the Dojo, so the loop is exercisable
        # offline. Deterministic on the rep utterance.
        rng = self._rng("stream", user[-300:])
        replies = [
            "That is fair, but I still need to understand what this costs us.",
            "We looked at something similar last year and it stalled. Why is this different?",
            "Walk me through how this actually changes my team's week.",
            "I hear you. My concern is the migration, honestly.",
            "Okay. What would the first thirty days look like?",
        ]
        for token in rng.choice(replies).split(" "):
            yield token + " "

    # -- schema-specific realism ----------------------------------------

    # -- transcript parsing ---------------------------------------------

    @staticmethod
    def _parse_lines(user: str) -> list[tuple[str, str, str]]:
        """Recover (segment_id, role, text) from the rendered transcript."""
        return re.findall(r"\[(s\d+)\]\s*\([\d:]+\)\s*(REP|BUYER):\s*(.+)", user)

    def _build_CallAnalysis(self, user: str, rng: random.Random):
        """Read the transcript and produce an analysis that reflects it.

        Keyword heuristics are obviously weaker than a language model, but they
        are honest about what they found and they fire on the same things the
        model would notice: an objection raised, a next step agreed, a
        three-minute monologue. That makes offline mode a real demonstration of
        the product rather than a wall of placeholders.
        """
        from ..schemas.analysis import (
            CallAnalysis,
            CallStage,
            Commitment,
            MeddicCoverage,
            MeddicItem,
            NextStep,
            Objection,
            StageSpan,
            TalkTrackIssue,
        )
        from ..schemas.common import EvidenceRef, ObjectionCategory, Severity

        lines = self._parse_lines(user)
        if not lines:
            return None

        call_id = "mock"
        buyer_lines = [(sid, text) for sid, role, text in lines if role == "BUYER"]
        rep_lines = [(sid, text) for sid, role, text in lines if role == "REP"]
        by_index = {sid: i for i, (sid, _, _) in enumerate(lines)}

        def ref(sid: str, text: str) -> EvidenceRef:
            return EvidenceRef(segment_id=sid, call_id=call_id, quote=text[:400])

        # -- objections, and whether the rep actually engaged -------------
        objections = []
        for idx, (sid, text) in enumerate(buyer_lines):
            category = _classify_objection(text)
            if not category:
                continue

            # The rep's next turn is the response. A response that asks a
            # question or names the tradeoff counts as engagement; one that
            # jumps straight to a discount does not.
            position = by_index[sid]
            response = next(
                ((s, t) for s, r, t in lines[position + 1 : position + 3] if r == "REP"),
                None,
            )
            handled, quality = False, 0
            if response is not None:
                reply = response[1]
                low = reply.lower()
                probes = "?" in reply or "compared to what" in low
                # A real answer to an objection carries either a question or a
                # concrete number. A fluent reassurance with neither -- "we work
                # with organisations of all sizes" -- is a deflection, and
                # scoring it as handled is how a tool ends up telling a rep
                # their worst call went well.
                concrete = bool(re.search(r"\d", reply))
                deflects = any(
                    cue in low
                    for cue in (
                        "discount", "flexibility there", "bring the annual number down",
                        "all sizes", "scale down", "more modern", "much cleaner",
                    )
                )
                if deflects:
                    handled, quality = False, 1
                elif probes:
                    handled, quality = True, 4
                elif concrete:
                    handled, quality = True, 3
                else:
                    handled, quality = False, 2

            objections.append(
                Objection(
                    id=f"o{idx}",
                    category=ObjectionCategory(category),
                    text=text[:180],
                    raised=ref(sid, text),
                    handled=handled,
                    handling_quality=quality,
                    handling=[ref(*response)] if response and handled else [],
                    note="Detected offline by keyword cue.",
                )
            )
            if len(objections) >= 5:
                break

        # -- next step, and whether the buyer agreed to it ----------------
        next_step = None
        for sid, text in reversed(rep_lines[-8:]):
            if not any(cue in text.lower() for cue in NEXT_STEP_CUES):
                continue
            position = by_index[sid]
            buyer_after = " ".join(
                t.lower() for s, r, t in lines[position:] if r == "BUYER"
            )
            next_step = NextStep(
                text=text[:200],
                evidence=ref(sid, text),
                has_date=bool(DATE_RE.search(text)),
                is_mutual=any(cue in buyer_after for cue in AGREEMENT_CUES),
            )
            break

        commitments = [
            Commitment(
                text=text[:160],
                by_role="rep",
                evidence=ref(sid, text),
                is_concrete=bool(DATE_RE.search(text)),
            )
            for sid, text in rep_lines
            if text.lower().startswith(("i will", "i would send", "let me send"))
        ][:4]

        # -- MEDDIC, by what was actually said ---------------------------
        joined = " ".join(t.lower() for _, _, t in lines)

        def covered_by(*cues: str) -> tuple[bool, str]:
            for sid, _, text in lines:
                low = text.lower()
                if any(cue in low for cue in cues):
                    return True, sid
            return False, ""

        def item(cues: tuple[str, ...]) -> MeddicItem:
            found, sid = covered_by(*cues)
            return MeddicItem(
                covered=found,
                confidence=0.65 if found else 0.15,
                evidence=[ref(sid, next(t for s, _, t in lines if s == sid))]
                if found
                else [],
                note="Offline keyword heuristic.",
            )

        meddic = MeddicCoverage(
            metrics=item(("thousand", "percent", "uplift", "worth")),
            economic_buyer=item(("sign it off", "budget", "approval", "cfo",
                                 "managing director", "board", "my boss")),
            decision_criteria=item(("would need to see", "success criterion",
                                    "what would convince", "judge", "bar here")),
            decision_process=item(("procurement", "legal", "process from",
                                   "budget process", "two weeks")),
            identify_pain=item(("we lose", "we missed", "problem", "fragile",
                                "went past", "falls off")),
            champion=item(("head of ops", "their lead", "she asked",
                           "actually asked me", "would use it")),
        )

        # -- issues and strengths, from measurable behaviour --------------
        issues: list[TalkTrackIssue] = []
        strengths: list[TalkTrackIssue] = []

        rep_words = sum(len(t.split()) for _, t in rep_lines)
        total_words = sum(len(t.split()) for _, _, t in lines)
        longest = max(rep_lines, key=lambda p: len(p[1].split()), default=None)

        if longest and len(longest[1].split()) > 220:
            issues.append(
                TalkTrackIssue(
                    title="Extended monologue without a handoff",
                    severity=Severity.HIGH,
                    explanation=(
                        f"A single unbroken turn of roughly "
                        f"{len(longest[1].split())} words. The buyer had no "
                        "opening to react, so nothing was learned from it."
                    ),
                    evidence=[ref(longest[0], longest[1])],
                    better_move=(
                        "Stop after the first idea and ask which part matters "
                        "to them before continuing."
                    ),
                )
            )

        if total_words and rep_words / total_words > 0.6:
            issues.append(
                TalkTrackIssue(
                    title="Rep dominated the conversation",
                    severity=Severity.MEDIUM,
                    explanation=(
                        f"The rep produced {round(rep_words / total_words * 100)}% "
                        "of the words on this call against a 43% benchmark."
                    ),
                    evidence=[],
                    better_move="Ask an open question and let the silence run.",
                )
            )

        open_questions = [
            (sid, text) for sid, text in rep_lines
            if text.strip().endswith("?")
            and text.lower().lstrip().startswith(("what", "how", "why", "who", "walk", "tell"))
        ]
        if len(open_questions) >= 4:
            strengths.append(
                TalkTrackIssue(
                    title="Sustained open-ended discovery",
                    severity=Severity.LOW,
                    explanation=(
                        f"{len(open_questions)} open questions, which is what "
                        "kept the buyer supplying detail rather than answering "
                        "yes or no."
                    ),
                    evidence=[ref(*open_questions[0])],
                    better_move="It worked because each question built on the last answer.",
                )
            )

        stages = []
        if lines:
            stages.append(
                StageSpan(
                    stage=CallStage.DISCOVERY if open_questions else CallStage.PITCH,
                    start_ms=0,
                    end_ms=0,
                    segment_ids=[sid for sid, _, _ in lines[: min(6, len(lines))]],
                )
            )

        # The headline is meant to name the thing that decided the call, so the
        # measured facts outrank the keyword findings. A rep who held 86% of
        # the floor for three unbroken minutes did not lose on a subtlety, and
        # leading with anything else would be misleading.
        unresolved = [o for o in objections if not o.handled]
        share = rep_words / total_words if total_words else 0.0
        longest_words = len(longest[1].split()) if longest else 0

        if longest_words > 220:
            headline = (
                f"A single {round(longest_words / 155)}-minute stretch with "
                f"{len(open_questions)} open question(s) asked"
            )
        elif share > 0.65:
            headline = f"The rep held {round(share * 100)}% of the conversation"
        elif unresolved:
            headline = f"Unresolved {unresolved[0].category.value} objection"
        elif next_step is None:
            headline = "No next step agreed"
        else:
            headline = "Buyer engaged and a next step was agreed"

        return CallAnalysis(
            call_id=call_id,
            summary=(
                f"Offline reading of a {len(lines)}-turn conversation. "
                f"{len(objections)} objection(s) detected, "
                f"{len([o for o in objections if o.handled])} engaged with. "
                "Connect a Qwen API key for genuine reasoning."
            ),
            headline=headline,
            stages=stages,
            objections=objections,
            meddic=meddic,
            commitments=commitments,
            next_step=next_step,
            buyer_signals=[],
            issues=issues,
            strengths=strengths,
        )

    def _build_PlayHarvest(self, user: str, rng: random.Random):
        """Detect narrative moves structurally.

        Only fires on the markers that distinguish a deliberate move from
        ordinary competence, so a feature-dump call correctly yields nothing --
        which is the behaviour that makes the playbook mean something.
        """
        from ..agents.playwright import PlayHarvest
        from ..schemas.play import PlayCandidate

        lines = self._parse_lines(user)
        if not lines:
            return None

        candidates: list[PlayCandidate] = []
        claimed: set[str] = set()

        for sid, role, text in lines:
            if role != "REP" or sid in claimed:
                continue
            low = text.lower()
            for kind, markers in PLAY_MARKERS.items():
                if not any(marker in low for marker in markers):
                    continue
                # A genuine move needs substance behind the marker.
                if len(text.split()) < 25:
                    continue
                # A proof point without a number is just an adjective, and
                # "went from" appears in plenty of ordinary sentences.
                if kind == "proof_point" and not re.search(r"\d", text):
                    continue
                claimed.add(sid)
                candidates.append(
                    PlayCandidate(
                        name=PLAY_TITLES[kind],
                        kind=kind,
                        thesis=PLAY_THESES[kind],
                        when_to_use=(
                            "When the buyer has described the problem but has "
                            "not yet felt what it costs them."
                        ),
                        beats=[
                            "Ask permission before telling it",
                            "Describe a comparable situation, not your product",
                            "Give the measured outcome",
                            "Hand the frame back with a question",
                        ],
                        template=text[:600],
                        quote=text[:600],
                        segment_ids=[sid],
                        effectiveness=0.75,
                    )
                )
                break

        return PlayHarvest(plays=candidates[:4])

    def _build_CoachingPlan(self, user: str, rng: random.Random):
        """Assemble a plan from the retrieved evidence in the prompt.

        The Coach hands the model measured gaps and real passages from winning
        calls; offline we parse those back out and stitch them into a script.
        The lines are the colleague's actual words, so the source references
        are genuine even though the arrangement is mechanical.
        """
        from ..schemas.coaching import (
            CoachingPlan,
            Drill,
            GeneratedScript,
            ScriptLine,
            ScriptSection,
            SkillGap,
            SourceRef,
        )
        from ..schemas.common import SkillAxis

        rep_name = (re.search(r"REP:\s*(.+)", user) or [None, "this rep"])[1].strip()

        gaps: list[SkillGap] = []
        for axis_name, rep_v, top_v, delta in re.findall(
            r"- (\w+): this rep ([\d.]+), team ceiling ([\d.]+) \(behind by ([\d.]+)\)",
            user,
        ):
            try:
                axis = SkillAxis(axis_name)
            except ValueError:
                continue
            gaps.append(
                SkillGap(
                    axis=axis,
                    rep_value=float(rep_v),
                    top_value=float(top_v),
                    delta=float(delta),
                    severity="high" if float(delta) >= 20 else "medium",
                    explanation=(
                        f"Trails the team ceiling on "
                        f"{axis.value.replace('_', ' ')} by {delta} points across "
                        "their analysed calls."
                    ),
                )
            )

        # Evidence blocks look like:
        #   [moment_id] Colleague | Account | for axis | similarity 0.82
        #     play: Name (id play_x)
        #     call_id: call_x
        #     segment_id: s0007
        #     text: ...
        evidence = []
        for block in re.split(r"\n(?=\[)", user):
            head = re.match(r"\[([\w:]+)\]\s*([^|]+)\|([^|]*)\|", block)
            if not head:
                continue
            text = re.search(r"text:\s*(.+)", block)
            evidence.append(
                {
                    "colleague": head.group(2).strip(),
                    "account": head.group(3).strip(),
                    "call_id": (re.search(r"call_id:\s*(\S+)", block) or [None, ""])[1],
                    "segment_id": (re.search(r"segment_id:\s*(\S+)", block) or [None, ""])[1],
                    "play_id": (re.search(r"\(id (\S+)\)", block) or [None, ""])[1],
                    "play_name": (re.search(r"play:\s*(.+?)\s*\(id", block) or [None, ""])[1],
                    "text": text.group(1).strip() if text else "",
                }
            )

        def source_for(item: dict) -> SourceRef:
            return SourceRef(
                play_id=item["play_id"] or None,
                play_name=item["play_name"],
                call_id=item["call_id"] or None,
                segment_id=item["segment_id"] or None,
                rep_name=item["colleague"],
                quote=item["text"][:400],
            )

        sections = [
            ScriptSection(
                label="Open on their problem, not your product",
                purpose="Earn the right to ask by showing you already listened.",
                lines=[
                    ScriptLine(
                        speaker="rep",
                        text=(
                            "Before I show you anything, can you walk me through "
                            "how this actually works for you today?"
                        ),
                        note="Ask, then stop talking. Let the silence run.",
                    ),
                    ScriptLine(
                        speaker="buyer_expected",
                        text="Answers at length. Do not interrupt to agree.",
                    ),
                ],
            )
        ]

        for item in evidence[:3]:
            sections.append(
                ScriptSection(
                    label=f"Borrow from {item['colleague'] or 'a colleague'}",
                    purpose=(
                        f"This is what worked on {item['account'] or 'a won deal'}."
                    ),
                    lines=[
                        ScriptLine(
                            speaker="rep",
                            text=item["text"][:420] or "See the source passage.",
                            note="Say it in your own words. Keep the structure.",
                            source=source_for(item),
                        ),
                        ScriptLine(
                            speaker="buyer_expected",
                            text="Pushes back or asks for the number. Stay in the frame.",
                        ),
                    ],
                )
            )

        sections.append(
            ScriptSection(
                label="Land a mutual next step",
                purpose="A next step the buyer also committed to, with a date on it.",
                lines=[
                    ScriptLine(
                        speaker="rep",
                        text=(
                            "Can we get you, me and whoever signs this off on a "
                            "call next week, and I will bring the model built on "
                            "your numbers?"
                        ),
                        note="Name a day. Do not leave with 'I will follow up'.",
                    ),
                ],
            )
        )

        drills = [
            Drill(
                title="Two questions before any answer",
                axis=gaps[0].axis if gaps else SkillAxis.DISCOVERY,
                instruction=(
                    "On your next three calls, ask two open questions before "
                    "you describe any part of the product."
                ),
                success_criteria="Talk ratio under 50% on all three.",
                persona_hint="A guarded operations lead who volunteers nothing.",
            ),
            Drill(
                title="Answer the objection with a question",
                axis=SkillAxis.OBJECTION_HANDLING,
                instruction=(
                    "When price comes up, ask what they are comparing it to "
                    "before offering any number."
                ),
                success_criteria="No discount offered before the comparison is named.",
                persona_hint="A budget holder who opens with 'that is too expensive'.",
            ),
        ]

        worst = max(gaps, key=lambda g: g.delta, default=None)
        return CoachingPlan(
            id="pending",
            rep_id="pending",
            rep_name=rep_name,
            generated_at="",
            diagnosis=(
                f"Offline reading: the largest measured gap is "
                f"{worst.axis.value.replace('_', ' ')}, "
                f"{worst.delta} points behind the team ceiling."
                if worst
                else "No measured gap against the team ceiling."
            ),
            gaps=gaps,
            prescribed_play_ids=[],
            script=GeneratedScript(
                id="pending",
                rep_id="pending",
                title="Grounded in your team's winning calls",
                scenario=(
                    "A discovery call where the buyer raises cost before you "
                    "have established what the problem is worth."
                ),
                sections=sections,
                grounded_in=[source_for(i) for i in evidence[:3]],
            ),
            drills=drills,
        )


class MockASR:
    """Turns a script file into a diarized transcript with plausible timings.

    Seed calls ship as scripts, so offline mode can produce a real transcript
    without ever touching audio -- which is how the whole demo stays runnable
    with no key.
    """

    name = "mock"
    WORDS_PER_MINUTE = 155.0

    def __init__(self, settings=None):
        self.settings = settings

    async def transcribe(
        self,
        audio_url: str,
        *,
        diarize: bool = True,
        language_hints: Sequence[str] = (),
    ) -> ASRResult:
        from pathlib import Path

        # A script beside the audio wins: that is how the seed corpus feeds
        # real dialogue through the pipeline without a key.
        script = Path(audio_url).with_suffix(".txt")
        if script.exists():
            return self.from_script(script.read_text(encoding="utf-8"))

        # Otherwise this is a genuine upload with no key configured. Rather
        # than fail -- which would leave a judge staring at a red stage on the
        # ingest screen -- synthesize a stand-in conversation so the whole DAG
        # still runs and the call page is populated. The transcript says
        # plainly what it is.
        log.warning(
            "offline transcription: no script beside %s, using the stand-in "
            "conversation. The uploaded audio was stored and NOT transcribed. "
            "Set DASHSCOPE_API_KEY, or another provider with diarization, to "
            "analyse real recordings.",
            audio_url,
        )
        return self.from_script(STAND_IN_CALL)

    @classmethod
    def from_script(cls, script: str) -> ASRResult:
        """Parse `SPEAKER: text` lines into timed, diarized sentences."""
        sentences: list[ASRSentence] = []
        cursor = 900  # a beat of room tone before anyone speaks
        rng = random.Random(hashlib.sha256(script.encode()).hexdigest()[:8])

        for raw in script.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([A-Za-z][\w .'-]*):\s*(.+)$", line)
            if not match:
                continue
            speaker, text = match.group(1).strip(), match.group(2).strip()
            speaker_id = 0 if speaker.upper().startswith("REP") else 1

            words = len(text.split())
            spoken_ms = int(words / cls.WORDS_PER_MINUTE * 60_000)
            spoken_ms = max(700, spoken_ms)

            sentences.append(
                ASRSentence(
                    begin_time=cursor,
                    end_time=cursor + spoken_ms,
                    text=text,
                    speaker_id=speaker_id,
                )
            )
            # A natural handoff pause, with enough variance that patience and
            # interruption metrics have something real to measure.
            cursor += spoken_ms + rng.randint(250, 1400)

        if not sentences:
            raise ValueError("script contained no parsable dialogue lines")

        return ASRResult(
            sentences=sentences,
            duration_ms=sentences[-1].end_time + 800,
            model="mock",
        )


class MockEmbeddings:
    """Hash-based embeddings.

    Not semantic, but stable and correctly shaped, so vector storage, cosine
    search and the whole retrieval path can be exercised and tested offline.
    Identical text always produces an identical vector.
    """

    name = "mock"

    def __init__(self, settings=None):
        self.dim = getattr(settings, "embedding_dim", 1024) if settings else 1024

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        rng = random.Random(hashlib.sha256(text.lower().encode()).hexdigest()[:16])
        vector = [rng.gauss(0.0, 1.0) for _ in range(self.dim)]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class MockTTS:
    name = "mock"

    def __init__(self, settings=None):
        self.settings = settings

    def voices(self) -> list[str]:
        return ["Cherry", "Ethan", "Jennifer", "Ryan"]

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        instruction: str = "",
        out_path: Optional[str] = None,
    ) -> bytes:
        raise NotImplementedError(
            "Speech synthesis needs a Qwen API key; offline mode uses scripts."
        )
