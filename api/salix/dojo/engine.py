"""The Dojo turn engine.

A practice session is a real conversation: the rep speaks, the buyer answers in
character, and a coach rail reacts live. Three design decisions shape it.

**The buyer holds a line.** The persona carries specific objections mined from
the rep's own lost calls, and the system prompt instructs it to deploy one and
*stay on it* until the rep does the work. A buyer who folds after one good
sentence teaches nothing.

**Nudges are deterministic.** The live coach fires on measurable conditions --
the rep has talked for two minutes without a question, an objection has been
raised twice and dodged twice, a prescribed play fits right now. Rules are
instant and never hallucinate, which is what a live rail needs.

**Scoring reuses the call metrics engine.** A Dojo session is converted into a
`Transcript` and run through exactly the same measurement code as a real
recording. Practice and reality are therefore measured identically, which is
the only way improvement in here means anything out there.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from ..metrics.engine import compute_metrics, is_question, split_sentences
from ..metrics.scorecard import build_scorecard
from ..providers.base import ProviderError
from ..providers.base import Providers
from ..schemas.call import Segment, Transcript
from ..schemas.common import SkillAxis, SpeakerRole
from ..schemas.dojo import (
    BuyerPersona,
    CoachNudge,
    DojoScore,
    DojoSession,
    DojoTurn,
)

log = logging.getLogger("salix.dojo.engine")

# Typed turns have no real timing, so a speaking rate is assumed in order to
# keep the transcript coherent. Spoken turns carry true timestamps from the
# browser and are always preferred.
ASSUMED_WPM = 155.0

MONOLOGUE_NUDGE_MS = 100_000
DODGE_LIMIT = 2


#: How to tell the model which language to answer in.
#:
#: Roman Urdu needs saying explicitly, and at length. Left to itself a model
#: handed Latin-script Urdu replies in Nastaliq -- it recognises the language
#: and reaches for its script -- which is unreadable to a rep who types in
#: Latin letters and useless for a floor that communicates this way.
LANGUAGE_RULES: dict[str, str] = {
    "en": (
        "LANGUAGE\n"
        "- Reply in English. Natural spoken business English, not written prose."
    ),
    "ur-roman": (
        "LANGUAGE\n"
        "- Reply in ROMAN URDU: Urdu written in Latin letters, the way "
        "Pakistani colleagues message each other. For example: "
        '"Dekhein, mujhe abhi is ki zaroorat nazar nahi aa rahi."\n'
        "- NEVER use Urdu or Arabic script. Not one word. If you write "
        "Nastaliq the answer is wrong, however correct the Urdu is.\n"
        "- Keep the English words Pakistani professionals actually use in "
        "speech -- price, budget, team, system, meeting, contract -- in "
        "English. Translating those into formal Urdu sounds like a textbook, "
        "not a buyer.\n"
        "- Spell phonetically and consistently. There is no official "
        "orthography; write it the way it sounds.\n"
        "- You are a woman, so use feminine agreement when the subject is "
        "YOU ALONE: \"main kar rahi hoon\", \"main soch rahi thi\" -- never "
        "\"main kar raha hoon\". This applies to \"main\" only. With "
        "\"hum\" say \"hum kar rahe hain\", and let other subjects agree "
        "with themselves: a system is \"chal raha hai\", a team is \"kaam "
        "kar rahi hai\"."
    ),
}

URDU_SCRIPT_RULES = (
    "LANGUAGE\n"
    "- Reply in Urdu script (Nastaliq). Natural spoken business Urdu.\n"
    "- Write naturally the way a Pakistani executive speaks.\n"
    "- Keep common English business terms (price, budget, team, system, meeting, contract) in their familiar usage.\n"
    "- You are a woman, so use feminine agreement for yourself.\n"
)


def persona_system_prompt(persona: BuyerPersona, language: str = "en", brief: str = "") -> str:
    objections = "\n".join(
        f"- [{o.category.value}, hardness {o.hardness:.1f}] {o.text}"
        for o in persona.objections
    )
    if language == "ur":
        rules = URDU_SCRIPT_RULES
    else:
        rules = LANGUAGE_RULES.get(language, LANGUAGE_RULES["en"])
    return f"""\
You are {persona.name}, {persona.title} at {persona.company}. You are on a call
with a salesperson. You are a real person having a real conversation, not an
assistant.

YOUR SITUATION
{persona.context}

YOUR DISPOSITION
{persona.disposition}

WHAT YOU PUSH BACK ON
These are your actual concerns. Deploy them naturally as the conversation gives
you the opening. Hardness is how firmly you hold each one, from 0 to 1.
{objections}

HOW TO BEHAVE
- Speak in first person, conversationally, the way people actually talk on a
  call. One to four sentences. Never monologue.
- Do not volunteer everything. Make the rep ask. If they ask a good, specific
  question, reward it with real detail.
- If they ask a lazy or generic question, give a short, unhelpful answer.
- When you raise an objection, hold it. Do not accept the first reassuring
  sentence. Accept it only when the rep has genuinely addressed the substance,
  or made you see the problem differently.
- If the rep talks at length without asking you anything, get shorter and less
  engaged. That is what real buyers do.
- You may warm up. If the rep does good work, let it show.
- Never break character. Never mention that you are an AI, a persona, or an
  exercise. Never coach the rep or comment on their technique.
- No stage directions, no asterisks, no narration. Only what you say out loud.

{brief}
{rules}
"""


class DojoEngine:
    def __init__(self, providers: Providers):
        self.providers = providers

    # -- session lifecycle ----------------------------------------------

    def start(
        self,
        rep_id: str,
        persona: BuyerPersona,
        scenario: str = "",
        language: str = "en",
    ) -> DojoSession:
        return DojoSession(
            id=f"dojo_{uuid.uuid4().hex[:10]}",
            rep_id=rep_id,
            persona=persona,
            # An unknown tag falls back to English rather than being passed
            # through to the prompt, where it would silently mean nothing.
            language=language if language in (*LANGUAGE_RULES, "ur") else "en",
            scenario=scenario or f"Discovery call with {persona.name} at {persona.company}",
            started_at=datetime.now(timezone.utc).isoformat(),
            turns=[],
            nudges=[],
        )

    # -- turns -----------------------------------------------------------

    async def buyer_reply(
        self, session: DojoSession, rep_text: str
    ) -> AsyncIterator[str]:
        """Stream the buyer's next line.

        History is passed as real chat turns rather than a flattened blob so the
        model keeps track of which objections it has already raised and which
        the rep has actually dealt with.
        """
        history = [
            {
                "role": "assistant" if turn.speaker == "buyer" else "user",
                "content": turn.text,
            }
            for turn in session.turns
        ]

        # A buyer speaks, so markdown is never part of the line. Nothing goes out until
        # there is a real word: under load a fallback model has answered "**: * *", which
        # the rep would otherwise read and hear as the buyer's reply.
        speaking = False
        held = ""
        async for token in self.providers.llm.stream(
            system=persona_system_prompt(session.persona, session.language, session.brief),
            user=rep_text,
            history=history,
            temperature=0.75,  # a person, not a template
            max_tokens=220,
        ):
            clean = token.replace("*", "").replace("#", "")
            if speaking:
                if clean:
                    yield clean
                continue
            held += clean
            if any(character.isalpha() for character in held):
                speaking = True
                yield held.lstrip(" :-\n\t")
        if not speaking:
            raise ProviderError(self.providers.llm.name, "the model returned no words", retryable=True)

    def record_turn(
        self,
        session: DojoSession,
        speaker: str,
        text: str,
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
    ) -> DojoTurn:
        """Append a turn, using real timings when the browser supplied them."""
        if start_ms is None:
            start_ms = session.turns[-1].end_ms + 700 if session.turns else 500
        if end_ms is None or end_ms <= start_ms:
            spoken = len(text.split()) / ASSUMED_WPM * 60_000
            end_ms = start_ms + int(max(600, spoken))

        turn = DojoTurn(
            index=len(session.turns),
            speaker=speaker,
            text=text.strip(),
            start_ms=start_ms,
            end_ms=end_ms,
        )
        session.turns.append(turn)
        return turn

    # -- the live coach rail ---------------------------------------------

    def nudges_for(self, session: DojoSession) -> list[CoachNudge]:
        """Rules that fire on the state of the conversation right now.

        Deterministic on purpose: a live rail must be instant and must never
        invent a criticism the rep can disprove by scrolling up.
        """
        fired: list[CoachNudge] = []
        index = len(session.turns)
        already = {(n.at_turn, n.title) for n in session.nudges}

        rep_turns = [t for t in session.turns if t.speaker == "rep"]
        buyer_turns = [t for t in session.turns if t.speaker == "buyer"]
        if not rep_turns:
            return fired

        def add(kind: str, title: str, detail: str, play_id: str | None = None):
            if (index, title) in already:
                return
            fired.append(
                CoachNudge(
                    at_turn=index, kind=kind, title=title, detail=detail, play_id=play_id
                )
            )

        # 1. Talking without asking.
        since_question = 0
        for turn in reversed(rep_turns):
            if any(is_question(s) for s in split_sentences(turn.text)):
                break
            since_question += turn.end_ms - turn.start_ms
        if since_question > MONOLOGUE_NUDGE_MS:
            add(
                "warning",
                "You have not asked anything in a while",
                f"{since_question // 1000}s of talking without a question. Stop and "
                "ask what matters most to them.",
            )

        # 2. An objection raised and dodged repeatedly.
        for objection in session.persona.objections:
            mentions = sum(
                1
                for t in buyer_turns
                if _mentions_category(t.text, objection.category.value)
            )
            if mentions < DODGE_LIMIT:
                continue
            # Same rule the scorer uses. A literal "?" was wrong here for the
            # same reason: dictation produces none, so this warning fired at a
            # rep who had already engaged -- telling them off for the thing
            # they had just done.
            engaged = any(
                _mentions_category(t.text, objection.category.value)
                and any(is_question(sentence) for sentence in split_sentences(t.text))
                for t in rep_turns
            )
            if not engaged:
                add(
                    "warning",
                    f"They have raised {objection.category.value} twice",
                    "You have not engaged with the substance. Ask what they are "
                    "comparing it to before you answer.",
                )

        # 3. The buyer is disengaging.
        if len(buyer_turns) >= 3:
            recent = [len(t.text.split()) for t in buyer_turns[-3:]]
            if recent[-1] < recent[0] * 0.5 and recent[-1] < 15:
                add(
                    "warning",
                    "They are giving you less and less",
                    "Their answers are getting shorter. Hand the floor back with "
                    "an open question.",
                )

        # 4. Genuine credit where it is due.
        last = rep_turns[-1]
        sentences = split_sentences(last.text)
        if sentences and all(is_question(s) for s in sentences) and len(last.text.split()) < 30:
            add(
                "praise",
                "Clean question, no preamble",
                "You asked and stopped. That is what creates room for them to talk.",
            )

        session.nudges.extend(fired)
        return fired

    def suggest_play(self, session: DojoSession, plays: list[dict]) -> Optional[CoachNudge]:
        """Surface the play that fits the objection currently on the table."""
        if not plays or not session.turns:
            return None
        last_buyer = next(
            (t for t in reversed(session.turns) if t.speaker == "buyer"), None
        )
        if last_buyer is None:
            return None

        for play in plays:
            trigger = (play.get("when_to_use") or "").lower()
            if not trigger:
                continue
            overlap = _keyword_overlap(last_buyer.text.lower(), trigger)
            if overlap >= 2:
                return CoachNudge(
                    at_turn=len(session.turns),
                    kind="play",
                    title=f"Reach for {play['name']}",
                    detail=play.get("thesis", ""),
                    play_id=play.get("id"),
                )
        return None

    # -- scoring ----------------------------------------------------------

    def to_transcript(self, session: DojoSession) -> Transcript:
        """Render the session as a call transcript so it can be measured by the
        same engine that measures real recordings."""
        return Transcript(
            call_id=session.id,
            segments=[
                Segment(
                    id=f"s{turn.index:04d}",
                    index=turn.index,
                    speaker_id=0 if turn.speaker == "rep" else 1,
                    role=SpeakerRole.REP if turn.speaker == "rep" else SpeakerRole.BUYER,
                    start_ms=turn.start_ms,
                    end_ms=turn.end_ms,
                    text=turn.text,
                )
                for turn in session.turns
            ],
        )

    def score(self, session: DojoSession, plays: list[dict] | None = None) -> DojoScore:
        transcript = self.to_transcript(session)
        if not transcript.segments:
            return DojoScore(overall=0.0, verdict="No turns recorded.")

        metrics = compute_metrics(transcript)
        card = build_scorecard(metrics)

        # Only what was actually put to them. Counting every objection the
        # persona was loaded with meant a rep who ended after four turns was
        # marked down for not answering something the buyer had never said --
        # measuring the script rather than the conversation.
        faced, handled = self._objections_handled(session)
        landed, missed = self._plays(session, plays or [])

        # The scorecard covers delivery; objection work is the point of the
        # exercise, so it is weighted alongside rather than folded in.
        objection_component = (handled / faced * 100) if faced else 60.0
        overall = round(
            0.6 * card.overall + 0.25 * objection_component + 0.15 * (len(landed) / 3 * 100),
            1,
        )
        overall = max(0.0, min(100.0, overall))

        return DojoScore(
            overall=overall,
            axes={a.axis: a.score for a in card.axes},
            objections_faced=faced,
            objections_handled=handled,
            plays_landed=landed,
            plays_missed=missed,
            talk_ratio_rep=metrics.talk_ratio_rep,
            verdict=self._verdict(metrics, handled, faced, overall),
        )

    def _objections_handled(self, session: DojoSession) -> tuple[int, int]:
        """How many objections were put to the rep, and how many they engaged.

        Engagement is a question on the subject, not a reassurance. Two ways to
        show it, because one alone is not enough.

        **Shared vocabulary.** The rep names the thing and asks about it in the
        same breath -- "on price, which number does your leadership care
        about?". Precise, and blind to the most common case.

        **Adjacency.** The buyer raises an objection and the rep's very next
        turn is a question. This exists because the best answers borrow none of
        the objection's words: told "it works well enough", a good rep asks
        "if the team got that time back, what would they do with it?" -- which
        is the status quo challenged on its own terms and shares not one term
        with it. Keyword matching scored that zero and told a rep who had done
        the right thing that they had engaged with nothing.

        A reassurance is still not credited by either route: "don't worry, most
        teams see value quickly" is not a question, and that is the whole
        distinction being drawn.
        """
        buyer_text = " ".join(
            t.text.lower() for t in session.turns if t.speaker == "buyer"
        )
        turns = session.turns

        def is_probe(turn) -> bool:
            return turn.speaker == "rep" and any(
                is_question(sentence) for sentence in split_sentences(turn.text)
            )

        faced = handled = 0
        for objection in session.persona.objections:
            category = objection.category.value
            if not _mentions_category(buyer_text, category):
                continue
            faced += 1

            named = any(
                _mentions_category(t.text, category) and is_probe(t) for t in turns
            )
            answered_next = any(
                t.speaker == "buyer"
                and _mentions_category(t.text, category)
                and index + 1 < len(turns)
                and is_probe(turns[index + 1])
                for index, t in enumerate(turns)
            )
            if named or answered_next:
                handled += 1
        return faced, handled

    def _plays(
        self, session: DojoSession, plays: list[dict]
    ) -> tuple[list[str], list[str]]:
        rep_text = " ".join(t.text.lower() for t in session.turns if t.speaker == "rep")
        landed, missed = [], []
        for play in plays[:6]:
            beats = [b.lower() for b in (play.get("beats") or [])]
            hits = sum(1 for b in beats if _keyword_overlap(rep_text, b) >= 2)
            (landed if hits >= 2 else missed).append(play["name"])
        return landed, missed

    def _verdict(self, metrics, handled: int, faced: int, overall: float) -> str:
        if metrics.talk_ratio_rep > 0.65:
            return (
                f"You held {round(metrics.talk_ratio_rep * 100)}% of the "
                "conversation. The buyer stopped telling you things."
            )
        if faced and handled == 0:
            return "You never engaged with a single objection on its own terms."
        if overall >= 75:
            return "Strong session. You asked, you listened, and you held the frame."
        if handled < faced:
            return f"You addressed {handled} of {faced} objections. The rest are still live."
        return "Solid. Keep the questions coming earlier in the call."


# --------------------------------------------------------------------------

#: Words and phrases that put a turn on the subject of an objection.
#:
#: This list was five words per category and matched by raw substring, which
#: failed in the least forgiving way possible: a buyer who said "it has worked
#: well enough", "it is not really broken", "we already have a rhythm" and
#: "I am not looking to overhaul our process" raised the status quo four times
#: and the engine detected it zero times -- because the term was "works" and
#: "worked" does not contain it. The rep was then told they had engaged with
#: nothing.
#:
#: So: real phrases people actually use, in both languages, with the inflected
#: forms spelled out. Explicit rather than stemmed, because stemming "work"
#: also matches "workflow" and a false positive here credits a rep for an
#: objection they never touched, which is the worse error of the two.
CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "price": (
        # English
        "price", "pricing", "priced", "cost", "costs", "costly", "expensive",
        "budget", "afford", "affordable", "discount", "spend", "spending",
        "investment", "premium", "cheaper", "quote", "quoted", "justify",
        "worth it", "too much", "steep", "dollar", "roi", "payback",
        # Roman Urdu
        "qeemat", "keemat", "mehnga", "mehngi", "mahanga", "kharcha", "kharch",
        "sasta", "daam", "paisa", "paise", "bajat",
    ),
    "timing": (
        "timing", "quarter", "next year", "next month", "right now", "later",
        "busy", "bad time", "not the time", "down the line", "revisit",
        "abhi nahi", "baad mein", "agle saal", "agle mahine", "waqt nahi",
        "filhaal", "masroof",
    ),
    "authority": (
        "sign off", "sign-off", "approval", "approve", "boss", "board", "cfo",
        "decision", "decide", "leadership", "stakeholder", "my team lead",
        "manzoori", "ijazat", "faisla", "sahab",
    ),
    "competition": (
        "competitor", "already use", "already using", "incumbent",
        "alternative", "another tool", "another vendor", "switch", "switching",
        "doosra", "dusra", "pehle se", "mukabla",
    ),
    "status_quo": (
        # The forms the failure above was made of.
        "works", "worked", "working", "well enough", "good enough",
        # "broken" alone, because an adverb slips in constantly -- "isn't
        # REALLY broken" -- and a substring match cannot see past it. It is
        # safe on its own: a buyer saying nothing is broken and a rep asking
        # what is broken are both squarely on the subject of the status quo.
        "broken",
        "fine as", "fine for now", "happy with", "no need", "don't need",
        "dont need", "no urgency", "not urgent", "rhythm", "used to it",
        "the way we", "how we do", "overhaul", "status quo", "as is",
        "change", "keeping up", "heads above water", "part of the job",
        # Roman Urdu
        "theek hai", "theek chal", "theek thaak", "aadat", "chal raha",
        "chal rahi", "zaroorat nahi", "masla nahi", "pareshani nahi",
        "kaam nikal", "sab theek",
    ),
    "trust": (
        "proof", "prove", "reference", "case study", "how do we know",
        "guarantee", "track record", "burned", "burnt", "promised",
        "sabit", "bharosa", "yaqeen", "tajurba",
    ),
    "fit": (
        "our size", "built for", "too big", "too small", "relevant",
        "not for us", "our industry", "our setup",
        "hamare liye", "hamari team", "munasib",
    ),
    "risk": (
        "risk", "risky", "migration", "disruption", "what if", "concerned",
        "worry", "worried", "headache", "another tool to the pile",
        "khatra", "nuqsan", "mushkil", "pareshani",
    ),
    "other": (),
}


def _mentions_category(text: str, category: str) -> bool:
    return any(term in text.lower() for term in CATEGORY_TERMS.get(category, ()))


def _keyword_overlap(text: str, phrase: str) -> int:
    """Count content words shared between a phrase and some text."""
    stop = {
        "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for",
        "with", "is", "are", "was", "it", "that", "this", "they", "you", "your",
        "not", "have", "has", "at", "as", "by", "be", "their", "them",
    }
    words = {w for w in phrase.split() if len(w) > 3 and w not in stop}
    return sum(1 for w in words if w in text)
