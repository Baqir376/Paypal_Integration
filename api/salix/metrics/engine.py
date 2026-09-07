"""The deterministic metrics engine.

No language model is consulted here. Everything is arithmetic over diarized
millisecond timestamps, which means every number Salix shows a sales manager
can be recomputed by hand from the transcript -- and is, in the unit tests.

The subtleties that separate this from a naive implementation:

* Overlapping speech is unioned, not summed, so ratios stay coherent.
* A two-word "mm-hmm" from the buyer does not end the rep monologue. Without
  that rule, longest-monologue collapses to noise on any engaged call.
* Patience only counts genuine buyer-to-rep handoffs. Interruptions produce
  negative gaps and are excluded rather than dragging the mean toward zero.
* Questions are detected structurally, because ASR punctuation is unreliable.
* Urdu and Roman Urdu are first-class. Urdu writes its full stop as U+06D4
  and its question mark as U+061F, and it is subject-object-verb, so the
  interrogative lands mid-sentence rather than opening it. Treating the
  language as an afterthought here does not produce slightly worse numbers --
  it produces zero questions on every Urdu call, which then scores the rep as
  though they never asked one.
"""

from __future__ import annotations

import re
import statistics

from ..schemas.call import Segment, Transcript
from ..schemas.common import SpeakerRole
from ..schemas.metrics import CallMetrics, Interruption, Monologue, TalkSlice
from . import benchmarks as B
from . import intervals as iv

# U+06D4 ARABIC FULL STOP and U+061F ARABIC QUESTION MARK end an Urdu
# sentence exactly as "." and "?" end an English one. Without them an entire
# Urdu turn arrives here as a single "sentence".
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?۔؟ە])\s+|\n+")

_FILLER_RE = re.compile("|".join(B.FILLER_PATTERNS), re.IGNORECASE)

# Unicode-aware, so Urdu tokenises. The previous pattern was ASCII-only, which
# made `is_backchannel` see zero words in "جی جی" and return False for every
# acknowledgement in the language. `[^\W_]` is "word character but not
# underscore", which keeps the old behaviour for English exactly.
_WORD_RE = re.compile(r"(?:[^\W_]|[’'])+", re.UNICODE)

# Any character in the Arabic/Urdu block. Used only to decide which set of
# language rules a sentence is judged by.
_URDU_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff]")

_QUESTION_MARKS = ("?", "؟")

# Roman Urdu is Urdu written in Latin script, so it cannot be told from English
# by character range. These are its closed-class words -- pronouns,
# postpositions, auxiliaries -- which appear in almost every sentence of it and
# essentially never in English. Content words are deliberately absent: a
# Pakistani rep speaking English says "budget" and "quarter" too.
_ROMAN_URDU_MARKERS: frozenset[str] = frozenset({
    # Auxiliaries and copulas
    "hai", "hain", "hoga", "hogi", "hoon", "hun", "tha", "thi",
    # Pronouns and possessives
    "aap", "tum", "hum", "mera", "meri", "hamara", "hamari",
    "aapka", "aapki", "aapke", "ye", "yeh", "wo", "woh", "kisi",
    # Postpositions -- the load-bearing ones
    "ka", "ki", "ke", "ko", "se", "mein", "tak", "liye", "bhi",
    # Interrogatives
    "kya", "kyun", "kyon", "kaise", "kahan", "kab", "kaun", "kitna", "kitni",
    # Negation, affirmation, connectives
    "nahi", "nahin", "haan", "acha", "theek", "bilkul", "shukriya",
    "abhi", "phir", "agar", "lekin", "magar", "aur", "jo", "jis",
    # Light verbs -- Urdu builds most verbs out of these
    "karte", "karta", "karti", "karna", "karen", "kiya",
    "sakte", "sakta", "sakti", "chahiye", "hota", "hoti", "hote",
    "zyada", "kuch", "koi", "sath", "baare",
    # Formal and polite register. Pakistani business correspondence is more
    # formal than the messaging register the rest of this list was built from,
    # and a politely worded sentence carries almost none of the casual
    # markers -- "Baraye meherbani commercial terms ki wazahat farma dein"
    # scored one hit across eight words and was read as English.
    "baraye", "meherbani", "meharbani", "wazahat", "farma", "farmaein",
    "dein", "dijiye", "kijiye", "guzarish", "darkhwast", "tashreef",
    "mutabiq", "mutaliq", "sahih", "durust", "izafi", "mazeed",
    "sahab", "janab", "ijazat", "manzoori", "tafseel",
    #
    # Deliberately absent: "the", "is", "us", "main", "par", "ho", "kam",
    # "sab", "so", "in", "us". Each is a Roman Urdu word AND a common English
    # one, and including them classified "The budget for this quarter covers
    # the Karachi and Lahore offices" as Urdu -- a Pakistani rep speaking
    # English, misread as speaking Urdu, and then scored against the wrong
    # pace band. An ambiguous marker is worse than a missing one.
})

#: How many markers a Latin-script utterance needs before it counts as Roman
#: Urdu, banded by length. A flat percentage is wrong at both ends: "kya hai"
#: is unmistakable on two words out of two, while a forty-word English
#: paragraph containing "aur" once is not Urdu at all.
#:
#: (max words, markers required)
_ROMAN_URDU_BANDS: tuple[tuple[int, int], ...] = ((3, 1), (6, 2))

#: Beyond the last band, both a count and a share must be cleared.
_ROMAN_URDU_LONG_HITS = 3
_ROMAN_URDU_LONG_SHARE = 0.22


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------


def detect_language(text: str) -> str:
    """Which language a body of speech is in: 'en', 'ur' or 'ur-roman'.

    Script settles Urdu outright. Roman Urdu shares its alphabet with English,
    so it is identified by the density of Urdu function words -- the ones that
    hold a sentence together and have no English equivalent spelling.

    Only used to pick a pace band. Nothing else in the engine cares, because
    nothing else in the engine is language-relative.
    """
    if not text.strip():
        return "en"

    urdu_chars = len(_URDU_RE.findall(text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    if urdu_chars > latin_chars * 0.5:
        return "ur"

    words = [w.strip(",.!?;:'\"") for w in text.lower().split()]
    words = [w for w in words if w]
    if not words:
        return "en"

    markers = sum(1 for w in words if w in _ROMAN_URDU_MARKERS)

    for max_words, needed in _ROMAN_URDU_BANDS:
        if len(words) <= max_words:
            return "ur-roman" if markers >= needed else "en"

    if markers >= _ROMAN_URDU_LONG_HITS and markers / len(words) >= _ROMAN_URDU_LONG_SHARE:
        return "ur-roman"
    return "en"


def is_backchannel(segment: Segment) -> bool:
    """True for acknowledgement noises that should not count as taking the floor."""
    if segment.duration_ms > B.BACKCHANNEL_MAX_MS:
        return False
    words = _WORD_RE.findall(segment.text.lower())
    if not words or len(words) > B.BACKCHANNEL_MAX_WORDS:
        return False
    return all(w in B.BACKCHANNEL_TOKENS for w in words)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _tokens(sentence: str) -> list[str]:
    """Words, stripped of the punctuation that clings to them in both scripts."""
    return [t.strip(",.۔،!?؟\"’'") for t in sentence.split() if t.strip()]


def _strip_lead(tokens: list[str]) -> list[str]:
    """Drop the discourse markers people open spoken sentences with.

    "And what does that cost you?" is an open question; "I mean, where does
    the time go?" is an open question. Matching on the raw prefix scores both
    as neither open nor closed, which quietly undercounts discovery on every
    call where the rep talks like a person instead of a form.

    Never strips the sentence to nothing -- a bare "right?" is still a turn.
    """
    out = list(tokens)
    stripping = True
    while stripping and out:
        stripping = False
        for marker in B.LEADING_DISCOURSE:
            parts = marker.split()
            if len(out) > len(parts) and out[: len(parts)] == parts:
                out = out[len(parts) :]
                stripping = True
                break
    return out


def _what_not_whether(tokens: list[str]) -> bool:
    """Is a sentence-initial "کیا" / "kya" the word "what", or the yes/no marker?

    Decided by what follows it: the yes/no marker introduces a subject, the
    interrogative introduces a verb. "کیا آپ..." is *whether*; "کیا ہوتا ہے"
    is *what*. Two words of context settle what no word list can.
    """
    if len(tokens) < 2:
        return False
    return tokens[1] not in B.YESNO_FOLLOWERS


def _clauses(sentence: str) -> list[list[str]]:
    """The sentence split into clauses, each tokenised and lead-stripped.

    Commas and their Urdu counterpart are the boundary. ASR drops them often
    enough that a clause split alone cannot be relied on -- see the
    subordinator rule in `classify_sentence` -- but when one is present it is
    the strongest signal available about where a new statement starts.
    """
    out = []
    for clause in re.split(r"[,،;؛]", sentence):
        head = _strip_lead(_tokens(clause.strip().lower()))
        if head:
            out.append(head)
    return out


def _open_probe_in(tokens: list[str], text: str) -> bool:
    """Does this clause open with something that invites a story?"""
    joined = " ".join(tokens)
    return any(joined.startswith(opener) for opener in B.OPEN_QUESTION_STARTERS)


def _wh_is_swallowed(tokens: list[str], index: int) -> bool:
    """Is the wh-word at `index` the object of a verb rather than a question?

    "I know what you mean" and "let me tell you how it works" both contain a
    wh-word and neither is asking anything. What gives it away is the word in
    front of it.
    """
    return index > 0 and tokens[index - 1] in B.WH_SWALLOWING_VERBS


def _is_imperative(tokens: list[str]) -> bool:
    """An auxiliary in first position that is not asking anything.

    "Do you have a budget?" and "Do not worry about it." open with the same
    word and are not the same kind of sentence. Treating the auxiliary alone
    as sufficient made every negated imperative a question, and the one that
    mattered was the canonical empty reassurance:

        Don't worry, most teams see value quickly.

    Counted as a question, that credits a rep with *engaging* an objection at
    the exact moment they dodged it -- inverting the one distinction the
    objection metric exists to draw. The contracted spelling escaped only
    because "don't" is not in the auxiliary list; the expanded one did not.

    Two shapes, both narrow, because a false negative here loses a real
    question and is its own kind of wrong:

        do/does/did + not + verb      -> imperative
        have + a/another + noun       -> "have a look at this"
    """
    if len(tokens) < 2:
        return False

    if tokens[1] in {"not", "never"}:
        # "Do you not have a budget?" keeps its subject and stays a question.
        return len(tokens) < 3 or tokens[2] not in B.SUBJECT_PRONOUNS

    if tokens[0] == "have" and tokens[1] in {"a", "another"}:
        return True

    return False


def classify_sentence(sentence: str) -> str:
    """One of "statement", "closed" or "open".

    Both `is_question` and `is_open_question` read from this, so the two can
    never disagree about whether something is a question -- which they briefly
    did, when only one of them learned to split clauses.

    The rules, in the order they are applied:

    1. A trailing "?" or "؟" makes it a question; what *kind* is still decided
       by the analysis below.
    2. An unambiguous interrogative anywhere in an Urdu sentence opens it,
       because Urdu is subject-object-verb and the question word lands in the
       middle.
    3. In Latin script, an open probe must *head a clause* -- otherwise
       "I know what you mean" reads as a question about "what".
    4. Unless the sentence opens with a subordinator ("if we did nothing how
       much would that cost"), in which case the real clause starts later and
       the probe is searched for across the whole sentence.
    5. An auxiliary verb in first position makes it closed.
    """
    s = sentence.strip().lower()
    if not s:
        return "statement"

    marked = s.endswith(_QUESTION_MARKS)
    tokens = _tokens(s)
    if not tokens:
        return "statement"
    core = _strip_lead(tokens)
    if not core:
        return "statement"

    # ---- Urdu script -------------------------------------------------
    if _URDU_RE.search(s):
        if any(t in B.URDU_OPEN_INTERROGATIVES for t in tokens):
            return "open"
        if core[0] in B.URDU_YESNO_OPENERS:
            # "کیا" opening: "what" if a verb follows, "whether" if a subject does.
            return "open" if _what_not_whether(core) else "closed"
        # Mid-sentence "کیا" is usually "what" -- but Urdu is verb-final, and
        # the same spelling is the past participle of "to do". "میں نے کام
        # کیا۔" is "I did the work", not a question about what. Position
        # settles it: as a verb it ends the clause, as "what" something
        # follows it.
        for i, t in enumerate(core[:-1], start=0):
            if i > 0 and t in B.URDU_YESNO_OPENERS:
                return "open"
        return "closed" if marked else "statement"

    # ---- Latin script: English and Roman Urdu ------------------------
    # Roman Urdu is not verb-second either, so its interrogatives are searched
    # across the sentence rather than required to open it.
    for i, t in enumerate(core):
        if t in B.ROMAN_OPEN_INTERROGATIVES:
            return "open"
        if t in B.ROMAN_WHAT:
            if i == 0:
                return "open" if _what_not_whether(core) else "closed"
            return "open"

    clauses = _clauses(s)

    # A probe that heads any clause opens the question.
    if any(_open_probe_in(c, s) for c in clauses):
        return "open"

    # A subordinate opener means the main clause has not started yet, so the
    # probe may be anywhere. ASR drops the comma that would have marked it.
    if core[0] in B.SUBORDINATORS:
        for i, t in enumerate(core):
            if i == 0:
                continue
            if _wh_is_swallowed(core, i):
                continue
            rest = " ".join(core[i:])
            if any(rest.startswith(opener) for opener in B.OPEN_QUESTION_STARTERS):
                return "open"

    if core[0] in B.CLOSED_QUESTION_STARTERS and not _is_imperative(core):
        return "closed"

    return "closed" if marked else "statement"


def is_question(sentence: str) -> bool:
    """Structural question detection.

    ASR punctuation is unreliable, so a trailing question mark is sufficient
    but never necessary.
    """
    return classify_sentence(sentence) != "statement"


def is_open_question(sentence: str) -> bool:
    """An open question invites a story; a closed one invites yes or no.

    The distinction is what separates a rep who is discovering from one who is
    confirming, so it is worth getting right in every language a call might be
    held in.
    """
    return classify_sentence(sentence) == "open"


def count_fillers(text: str) -> int:
    return len(_FILLER_RE.findall(text))


# --------------------------------------------------------------------------
# Turn structure
# --------------------------------------------------------------------------


def monologue_runs(segments: list[Segment]) -> list[list[Segment]]:
    """Runs of one speaker holding the floor, tolerant of backchannels.

    This answers "how long did one person speak without genuinely yielding",
    which is the question a sales manager is actually asking when they look at
    longest-monologue.
    """
    ordered = sorted(segments, key=lambda s: (s.start_ms, s.end_ms))
    runs: list[list[Segment]] = []
    current: list[Segment] = []

    for seg in ordered:
        if not current:
            current = [seg]
            continue
        holder_role = current[-1].role
        if seg.role is holder_role:
            gap = seg.start_ms - current[-1].end_ms
            if gap <= B.TURN_GAP_TOLERANCE_MS:
                current.append(seg)
            else:
                runs.append(current)
                current = [seg]
        elif is_backchannel(seg):
            continue  # acknowledged, floor not surrendered
        else:
            runs.append(current)
            current = [seg]

    if current:
        runs.append(current)
    return runs


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------


def compute_metrics(
    transcript: Transcript, duration_ms: int | None = None
) -> CallMetrics:
    segments = sorted(transcript.segments, key=lambda s: (s.start_ms, s.end_ms))
    if not segments:
        # A recording with a known length and no speech in it is silence, all
        # of it. Reporting zero here hid exactly the case worth seeing: a
        # forty-minute call where the microphone was never live looked
        # identical to a call that was never uploaded.
        return CallMetrics(
            call_id=transcript.call_id,
            duration_ms=duration_ms or 0,
            silence_ms=duration_ms or 0,
        )

    last_end = max(s.end_ms for s in segments)
    total_ms = max(duration_ms or 0, last_end)

    rep = [s for s in segments if s.role is SpeakerRole.REP]
    buyer = [s for s in segments if s.role is SpeakerRole.BUYER]

    rep_iv = [(s.start_ms, s.end_ms) for s in rep]
    buyer_iv = [(s.start_ms, s.end_ms) for s in buyer]
    all_iv = [(s.start_ms, s.end_ms) for s in segments]

    rep_ms = iv.total(rep_iv)
    buyer_ms = iv.total(buyer_iv)
    speech_ms = iv.total(all_iv)
    silence_ms = max(0, total_ms - speech_ms)

    voiced = rep_ms + buyer_ms
    talk_ratio_rep = (rep_ms / voiced) if voiced else 0.0

    metrics = CallMetrics(
        call_id=transcript.call_id,
        duration_ms=total_ms,
        rep_talk_ms=rep_ms,
        buyer_talk_ms=buyer_ms,
        silence_ms=silence_ms,
        talk_ratio_rep=round(min(1.0, talk_ratio_rep), 4),
    )

    _apply_monologues(metrics, segments)
    _apply_reciprocity(metrics, segments, total_ms)
    _apply_discovery(metrics, rep, total_ms)
    _apply_delivery(metrics, rep, buyer, rep_ms, buyer_ms)
    _apply_dead_air(metrics, all_iv)
    metrics.timeline = build_timeline(rep_iv, buyer_iv, total_ms)
    return metrics


def _apply_monologues(metrics: CallMetrics, segments: list[Segment]) -> None:
    runs = monologue_runs(segments)
    found: list[Monologue] = []

    for run in runs:
        start = run[0].start_ms
        end = run[-1].end_ms
        duration = end - start
        if duration < B.MONOLOGUE_THRESHOLD_MS:
            continue
        found.append(
            Monologue(
                speaker_role=run[0].role.value,
                start_ms=start,
                end_ms=end,
                duration_ms=duration,
                segment_ids=[s.id for s in run],
                opening_words=" ".join(run[0].text.split()[:12]),
            )
        )

    found.sort(key=lambda m: m.duration_ms, reverse=True)
    metrics.monologues = found[:10]

    rep_runs = [r for r in runs if r[0].role is SpeakerRole.REP]
    if rep_runs:
        longest = max(rep_runs, key=lambda r: r[-1].end_ms - r[0].start_ms)
        metrics.longest_monologue_ms = longest[-1].end_ms - longest[0].start_ms
        metrics.longest_monologue_at_ms = longest[0].start_ms

    metrics.monologues_over_threshold = sum(
        1 for m in found if m.speaker_role == SpeakerRole.REP.value
    )


def _apply_reciprocity(
    metrics: CallMetrics, segments: list[Segment], total_ms: int
) -> None:
    patience_gaps: list[float] = []
    interruptions: list[Interruption] = []
    switches = 0

    for prev, cur in zip(segments, segments[1:]):
        if cur.role is not prev.role and not is_backchannel(cur):
            switches += 1

        overlap = iv.overlap_ms(
            (prev.start_ms, prev.end_ms), (cur.start_ms, cur.end_ms)
        )
        if overlap >= B.INTERRUPTION_MIN_OVERLAP_MS and cur.role is not prev.role:
            interruptions.append(
                Interruption(
                    at_ms=cur.start_ms,
                    by_role=cur.role.value,
                    segment_id=cur.id,
                    overlap_ms=overlap,
                )
            )
            continue

        # A genuine handoff: the buyer finished and the rep picked up cleanly.
        if prev.role is SpeakerRole.BUYER and cur.role is SpeakerRole.REP:
            gap = cur.start_ms - prev.end_ms
            if gap >= 0:
                patience_gaps.append(float(gap))

    metrics.patience_ms = (
        round(statistics.fmean(patience_gaps), 1) if patience_gaps else 0.0
    )
    metrics.interruptions = interruptions[:25]
    metrics.interruptions_by_rep = sum(
        1 for i in interruptions if i.by_role == SpeakerRole.REP.value
    )
    metrics.interruptions_by_buyer = sum(
        1 for i in interruptions if i.by_role == SpeakerRole.BUYER.value
    )
    minutes = total_ms / 60000.0
    metrics.switches_per_min = round(switches / minutes, 2) if minutes else 0.0


def _apply_discovery(metrics: CallMetrics, rep: list[Segment], total_ms: int) -> None:
    questions = 0
    open_questions = 0
    for seg in rep:
        for sentence in split_sentences(seg.text):
            if is_question(sentence):
                questions += 1
                if is_open_question(sentence):
                    open_questions += 1

    minutes = total_ms / 60000.0
    metrics.rep_question_count = questions
    metrics.rep_question_rate_per_min = (
        round(questions / minutes, 2) if minutes else 0.0
    )
    metrics.open_question_ratio = (
        round(open_questions / questions, 3) if questions else 0.0
    )


def _apply_delivery(
    metrics: CallMetrics,
    rep: list[Segment],
    buyer: list[Segment],
    rep_ms: int,
    buyer_ms: int,
) -> None:
    rep_words = sum(s.word_count for s in rep)
    buyer_words = sum(s.word_count for s in buyer)

    metrics.rep_wpm = round(rep_words / (rep_ms / 60000.0), 1) if rep_ms else 0.0
    # Judged on the rep's own speech, not the buyer's: this decides which pace
    # band the rep is scored against, and a buyer who answers in English does
    # not make an Urdu-speaking rep English.
    metrics.language = detect_language(" ".join(s.text for s in rep))
    metrics.buyer_wpm = (
        round(buyer_words / (buyer_ms / 60000.0), 1) if buyer_ms else 0.0
    )

    fillers = sum(count_fillers(s.text) for s in rep)
    metrics.filler_rate_rep = (
        round(fillers / rep_words * 100, 2) if rep_words else 0.0
    )


def _apply_dead_air(metrics: CallMetrics, all_iv: list[tuple[int, int]]) -> None:
    """Longest silence *between* utterances.

    Leading and trailing silence is excluded on purpose -- that is recording
    padding, not an awkward pause on the call.
    """
    merged = iv.merge(all_iv)
    if len(merged) < 2:
        metrics.longest_dead_air_ms = 0
        return
    internal = [b_start - a_end for (_, a_end), (b_start, _) in zip(merged, merged[1:])]
    metrics.longest_dead_air_ms = max(internal) if internal else 0


def build_timeline(
    rep_iv: list[tuple[int, int]],
    buyer_iv: list[tuple[int, int]],
    total_ms: int,
) -> list[TalkSlice]:
    """Bucket the call for the Conversation Helix.

    A bucket with no speech reports a neutral 0.5 share, so silence renders as
    a narrow untwisted ribbon rather than leaning toward whoever spoke last.
    """
    if total_ms <= 0:
        return []

    buckets = int(round(total_ms / B.TIMELINE_TARGET_BUCKET_MS))
    buckets = max(B.TIMELINE_MIN_BUCKETS, min(B.TIMELINE_MAX_BUCKETS, buckets))
    width = total_ms / buckets

    rep_merged = iv.merge(rep_iv)
    buyer_merged = iv.merge(buyer_iv)

    raw: list[tuple[int, int, int, int]] = []
    peak = 1.0

    for i in range(buckets):
        start = int(i * width)
        end = int((i + 1) * width) if i < buckets - 1 else total_ms
        r = sum(iv.overlap_ms(x, (start, end)) for x in rep_merged)
        b = sum(iv.overlap_ms(x, (start, end)) for x in buyer_merged)
        raw.append((start, end, r, b))
        peak = max(peak, float(r + b))

    slices: list[TalkSlice] = []
    for start, end, r, b in raw:
        voiced = r + b
        slices.append(
            TalkSlice(
                start_ms=start,
                end_ms=end,
                rep_ms=r,
                buyer_ms=b,
                rep_share=round((r / voiced) if voiced else 0.5, 4),
                energy=round(min(1.0, voiced / peak), 4),
            )
        )
    return slices
