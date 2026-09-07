"""Benchmarks and thresholds, in one place.

Every constant here is either sourced from published conversation-intelligence
research or is an explicitly-labelled house rule. They live together so that
retuning the product's opinions never requires touching the measurement code.

Sources
-------
Talk-to-listen: analysis of B2B sales calls puts the highest-converting rep
share at ~43% (43:57 rep:buyer). Gong Labs, "Mastering the talk-to-listen
ratio in sales calls".
Monologue: rep speech beyond ~2 minutes without a handoff correlates with lost
deals; 2.5 minutes is treated as the hard ceiling.
Patience: waiting 0.6-1.0s after the buyer stops separates top performers from
the rest; below that reads as interrupting, above as disengaged.
"""

from __future__ import annotations

from .pace_corpus import derive_ratios as _derive_pace_ratios

# --- Floor control ------------------------------------------------------
TALK_RATIO_TARGET = 0.43
TALK_RATIO_TOLERANCE = 0.07  # 36%-50% is treated as on-target
TALK_RATIO_HARD_CEILING = 0.65

MONOLOGUE_WARN_MS = 120_000
MONOLOGUE_FAIL_MS = 150_000
MONOLOGUE_THRESHOLD_MS = 90_000  # counted in `monologues_over_threshold`

# A short utterance from the other side is a backchannel ("mm-hmm", "right"),
# not a genuine handoff, so it must not break a monologue run.
BACKCHANNEL_MAX_MS = 1_500
BACKCHANNEL_MAX_WORDS = 4

# Gap between same-speaker segments that still counts as one continuous turn.
TURN_GAP_TOLERANCE_MS = 2_000

# --- Reciprocity --------------------------------------------------------
PATIENCE_TARGET_MS = 800.0
PATIENCE_FLOOR_MS = 600.0
PATIENCE_CEILING_MS = 1_400.0

# Overlap below this is diarization jitter, not a real interruption.
INTERRUPTION_MIN_OVERLAP_MS = 250

SWITCHES_PER_MIN_TARGET = 4.0

# --- Discovery ----------------------------------------------------------
QUESTION_RATE_TARGET = 2.0  # rep questions per minute on a discovery call
QUESTION_RATE_FLOOR = 1.0
OPEN_QUESTION_TARGET = 0.6

# --- Delivery -----------------------------------------------------------
# --- Pace ---------------------------------------------------------------
#
# The English band. Everything else is derived from it, because words per
# minute is not comparable between languages: Urdu needs about a fifth more
# words to carry the same content, so a rep speaking it at a perfectly
# ordinary pace measures ~20% "faster" on a scale calibrated for English.
#
# The multiplier comes from `pace_corpus.derive_ratios()` -- parallel sales
# speech that ships in this repository -- rather than from a published figure,
# because the published figures for Urdu disagree by a factor of two. See that
# module for the reasoning and the citation behind it.
WPM_TARGET_LOW = 140.0
WPM_TARGET_HIGH = 175.0

_PACE_RATIOS = _derive_pace_ratios()

#: Language tag -> (low, high) words per minute.
WPM_TARGETS: dict[str, tuple[float, float]] = {
    tag: (round(WPM_TARGET_LOW * r, 1), round(WPM_TARGET_HIGH * r, 1))
    for tag, r in _PACE_RATIOS.items()
}


#: Languages whose band comes from published research on real recordings.
#: Their ratio is exactly 1.0 by definition and the band is used as-is.
PACE_CALIBRATED: frozenset[str] = frozenset({"en"})

#: How well the Urdu word ratio is actually known.
#:
#: Four independent estimates — two synthetic parallel corpora and two matched
#: calls — give 1.010, 1.116, 1.137 and 1.154. They disagree by more than the
#: correction itself, which is what makes a single point estimate unusable:
#: applying 1.137 produced up to 13.9 points of systematic bias on the pace
#: axis, in both directions depending on whether the call was fast or slow.
#:
#: So the band spans the interval instead of sitting at its midpoint. A rep
#: speaking at any reasonable rate falls inside it and is neither rewarded nor
#: punished for our uncertainty; someone genuinely racing is still caught.
#:
#: Narrow this the moment `pace_corpus.PARALLEL` holds real call transcripts.
#: The interval every attempt to calibrate Urdu landed in: 1.010, 1.116, 1.137
#: and 1.154, from two synthetic corpora and two matched calls.
#:
#: They are kept for the record and for the band shown in the interface, but
#: they do not decide a score. Every one of them came from parallel text
#: written for the purpose, so the spread measures the author's phrasing rather
#: than the language -- and it is wider than the correction it was meant to
#: justify. Scoring on any single value left up to 15 points of bias on the
#: pace axis, in whichever direction the call happened to fall.
#:
#: Replace this with a ratio measured from real recorded Urdu calls, add "ur"
#: to PACE_CALIBRATED, and the term scores normally.
PACE_RATIO_BOUNDS: dict[str, tuple[float, float]] = {
    "ur": (1.01, 1.16),
    "ur-roman": (1.01, 1.16),
}


def wpm_band(language: str) -> tuple[float, float]:
    """The pace band a call in this language is judged against.

    For a calibrated language this is the researched band. For any other it is
    widened to the interval the ratio is known to within, so the score never
    turns on a number we cannot pin down.
    """
    if language in PACE_CALIBRATED:
        return (WPM_TARGET_LOW, WPM_TARGET_HIGH)

    low_ratio, high_ratio = PACE_RATIO_BOUNDS.get(language, (1.0, 1.0))
    return (
        round(WPM_TARGET_LOW * low_ratio, 1),
        round(WPM_TARGET_HIGH * high_ratio, 1),
    )


def pace_is_scored(language: str) -> bool:
    """Is this language's band exact, rather than an estimate?

    Delivery rate contributes to the score in every language. What this
    decides is whether the band can be trusted as a single figure, or whether
    the rep should be given the benefit of the interval around it.
    """
    return language in PACE_CALIBRATED
FILLER_RATE_GOOD = 1.5   # per 100 words
FILLER_RATE_BAD = 5.0
DEAD_AIR_WARN_MS = 6_000

# --- Timeline resolution ------------------------------------------------
TIMELINE_MIN_BUCKETS = 24
TIMELINE_MAX_BUCKETS = 140
TIMELINE_TARGET_BUCKET_MS = 5_000

# --- Lexicons -----------------------------------------------------------
#
# Salix is used on Pakistani sales floors, where a single call moves between
# English, Urdu and Roman Urdu -- often inside one sentence. Every lexicon
# below therefore has three sections, and the English one is never modified:
# an English call must measure identically before and after this was added.
#
# Roman Urdu is Urdu vocabulary in Latin script. It tokenises like English and
# usually carries ASCII punctuation, so it mostly needs vocabulary rather than
# new machinery. Urdu script needs both.

FILLER_PATTERNS: tuple[str, ...] = (
    # English
    r"\bum+\b", r"\buh+\b", r"\ber+\b", r"\bhmm+\b",
    r"\byou know\b", r"\bi mean\b", r"\bsort of\b", r"\bkind of\b",
    r"\bbasically\b", r"\bliterally\b", r"\bobviously\b", r"\bto be honest\b",
    r"\bat the end of the day\b",
    # Tag questions used as filler. Anchored to the end of a clause rather
    # than to a literal question mark: ASR drops the mark constantly, so
    # "that makes sense, right" scored zero while "...right?" scored one --
    # the same tic, counted differently depending on punctuation nobody said.
    # "right" mid-sentence ("the right approach") stays an ordinary word.
    r"\bright(?=\s*[?.!]?\s*$)", r"\bmake sense(?=\s*[?.!]?\s*$)",
    # Urdu. \b is Unicode-aware for str patterns in Python 3, so these anchor
    # the same way the English ones do.
    r"\bیعنی\b",      # "that is to say" -- the exact analogue of "I mean"
    r"\bمطلب\b",      # "meaning" -- used as a discourse filler, not a noun
    r"\bدیکھیں\b",    # "look" / "see" -- the Urdu "you know"
    r"\bکہنے کا مطلب\b",
    # Roman Urdu
    r"\bmatlab\b", r"\bya[ae]?ni\b", r"\bdekhen\b", r"\bdekhiye\b",
    r"\bkehne ka matlab\b",
)

# Discourse markers that open a spoken sentence without changing what it is.
# People do not talk in written sentences: "And what does that cost you?" is
# an open question, and matching only on the prefix scores it as neither open
# nor closed. Longest first, so "i mean" is tried before "i".
LEADING_DISCOURSE: tuple[str, ...] = (
    "you know", "i mean", "and then", "ok so", "okay so",
    "and", "so", "but", "now", "well", "also", "then", "just",
    "ok", "okay", "right", "look", "listen",
    # Urdu and Roman Urdu equivalents
    "اور", "تو", "پھر", "اچھا", "دیکھیں", "یعنی", "مطلب",
    "aur", "phir", "acha", "dekhen", "matlab", "yaani",
)

# --- Question detection -------------------------------------------------
#
# English is verb-second, so an interrogative reliably opens the sentence and
# `startswith` is the right test. Urdu is subject-object-verb: the question
# word lands in the middle or near the end --
#
#     آج جب ڈیل رک جاتی ہے تو کیا ہوتا ہے؟
#     (when a deal stalls today, what happens?)
#
# -- so for Urdu these are matched anywhere in the sentence instead.

OPEN_QUESTION_STARTERS: tuple[str, ...] = (
    "what", "how", "why", "when", "where", "who", "which",
    "tell me", "walk me", "describe", "help me understand",
    "talk me through", "what does", "in what way",
    # Soft openers. A rep asking "any thoughts on the timeline" is running
    # discovery just as much as one asking "what do you think", and the
    # wh-word test misses every one of them.
    "any thoughts", "any concerns", "any questions", "any reaction",
    "your thoughts", "thoughts on", "how about", "what about",
    "give me a sense", "paint me a picture", "say more",
)

# Words that open a subordinate clause. When a sentence begins with one, the
# main clause -- and with it the interrogative -- arrives later:
#
#     "If we did nothing how much would that cost"
#
# ASR drops commas constantly, so the clause boundary cannot be relied on;
# a leading subordinator is the signal that the sentence has not started
# saying its real business yet.
SUBORDINATORS: tuple[str, ...] = (
    "if", "when", "once", "after", "before", "unless", "assuming",
    "given", "since", "while", "supposing", "in case",
)

# Verbs that swallow a wh-word into a statement: "I know what you mean",
# "let me tell you how it works". A wh-word appearing after one of these is
# not asking anything.
WH_SWALLOWING_VERBS: frozenset[str] = frozenset({
    "know", "knew", "understand", "understood", "see", "saw", "remember",
    "realise", "realize", "forget", "forgot", "tell", "told", "showed",
    "explained", "explain", "said", "say", "think", "thought", "wonder",
    "heard", "hear", "learned", "learnt", "noticed",
})

#: Subjects that keep a negated auxiliary interrogative.
#:
#: "Do not worry" is an instruction; "do you not have a budget" is a question.
#: What separates them is whether somebody is being asked about.
SUBJECT_PRONOUNS: frozenset[str] = frozenset({
    "you", "we", "they", "it", "he", "she", "i", "that", "this",
    "these", "those", "there", "your", "our", "their",
})

CLOSED_QUESTION_STARTERS: tuple[str, ...] = (
    "is", "are", "was", "were", "do", "does", "did", "can", "could",
    "will", "would", "should", "have", "has", "had", "am", "may", "might",
)

# Urdu interrogatives with no non-interrogative reading. Their presence
# anywhere in a sentence makes it a question, and an open one.
URDU_OPEN_INTERROGATIVES: tuple[str, ...] = (
    "کیوں",      # why
    "کیسے",      # how
    "کہاں",      # where
    "کب",        # when
    "کون",       # who
    "کونسا", "کونسی", "کونسے",   # which
    "کتنا", "کتنی", "کتنے",      # how much / how many
    # Imperative probes. Not interrogatives grammatically, but they do the
    # same work in a call -- the Urdu equivalents of "tell me more".
    "بتائیے", "بتائیں", "بتاؤ",
    "سمجھائیے", "سمجھائیں",      # explain to me
    "وضاحت",                      # clarify
    "رائے",                       # "your view on ..." -- the soft open probe
)

# کیا is deliberately NOT in the list above. It is both "what" and the past
# participle of "to do", so "میں نے کام کیا" ("I did the work") is a
# statement. It is counted only in the sentence-initial yes/no position --
#
#     کیا آپ کے پاس بجٹ ہے؟   (do you have budget?)
#
# -- where it is unambiguous. Mid-sentence "کیا" questions almost always carry
# the question mark, which is checked first anyway. A false positive inflates
# a rep's question rate, and for a coaching product that is worse than a miss.
URDU_YESNO_OPENERS: tuple[str, ...] = ("کیا",)

# Sentence-initial "کیا" / "kya" is ambiguous in a way no word list can settle
# on its own:
#
#     کیا آپ کے پاس بجٹ ہے؟   do you have budget?      -- yes/no, closed
#     کیا ہوتا ہے جب ڈیل رکتی ہے؟   what happens when a deal stalls?  -- open
#
# What separates them is the word after it. The yes/no marker is followed by
# the subject; the interrogative "what" is followed by the verb. So the
# pronouns and determiners that can open a subject are listed, and anything
# else after "کیا" means it is doing the work of "what".
YESNO_FOLLOWERS: frozenset[str] = frozenset({
    # Urdu pronouns and determiners
    "آپ", "تم", "تو", "ہم", "میں", "یہ", "وہ", "اس", "ان", "کوئی", "کسی",
    "آپکے", "آپکا", "آپکی", "میرا", "ہمارے", "ہمارا",
    # Roman Urdu
    "aap", "ap", "tum", "hum", "hm", "main", "mein", "ye", "yeh", "wo", "woh",
    "is", "us", "in", "koi", "kisi", "aapke", "aapka", "aapki", "humara",
})

ROMAN_OPEN_INTERROGATIVES: tuple[str, ...] = (
    "kyun", "kyon", "kiun", "kyu",
    "kaise", "kese", "kaisay",
    "kahan", "kahaan",
    "kab",
    "kaun", "kon",
    "kitna", "kitni", "kitne", "kitnay",
    "batayen", "bataiye", "bataye", "batao",
    "samjhaiye", "samjhayen",
    "raye",
)

# In Roman Urdu the ambiguity above disappears: the verb is written "kiya",
# the interrogative "kya". So this one is safe anywhere in the sentence.
ROMAN_WHAT: tuple[str, ...] = ("kya",)

BACKCHANNEL_TOKENS: frozenset[str] = frozenset({
    # English
    "mm", "mmhmm", "mhm", "uh", "huh", "yeah", "yep", "yes", "ok", "okay",
    "right", "sure", "got", "it", "gotcha", "true", "exactly", "totally",
    "absolutely", "cool", "nice", "wow", "hmm", "i", "see", "makes", "sense",
    # Urdu. "ہے" is an ordinary copula, but the guard around this set is
    # already narrow -- under 1.5 seconds, at most four words, and *every*
    # word drawn from here -- so "ٹھیک ہے" passes and a real short sentence
    # does not.
    "جی", "ہاں", "جی_ہاں", "اچھا", "ٹھیک", "ہے", "بالکل", "صحیح", "درست",
    "اوکے", "شکریہ",
    # Roman Urdu
    "ji", "haan", "han", "acha", "accha", "achha", "theek", "thik", "thk",
    "bilkul", "sahi", "durust", "shukriya",
    # The Roman copula, matching "ہے" above. Only ever admitted as part of an
    # all-backchannel utterance ("theek hai"), never on its own merit.
    "hai",
})
