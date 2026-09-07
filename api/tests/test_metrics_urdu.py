# -*- coding: utf-8 -*-
"""The metrics engine in Urdu and Roman Urdu.

Salix is used on Pakistani sales floors. A call there moves between English,
Urdu and Roman Urdu — often inside one sentence — and the engine treating any
of them as an afterthought does not produce slightly worse numbers, it
produces *zero* questions on an Urdu call and then scores the rep as though
they never asked one.

Every expectation here is a judgement about the language, so each case carries
its English gloss. If a case needs a comment explaining why the answer is what
it is, the rule behind it is probably wrong.
"""

from __future__ import annotations

import pytest

from salix.metrics import benchmarks as B
from salix.metrics.engine import (
    compute_metrics,
    count_fillers,
    detect_language,
    is_backchannel,
    is_open_question,
    is_question,
    split_sentences,
)
from salix.metrics.pace_corpus import derive_ratios
from salix.metrics.scorecard import score_pace
from salix.schemas.call import Transcript
from salix.schemas.call import Segment
from salix.schemas.common import SpeakerRole


def seg(text: str, *, start: int = 0, end: int = 700) -> Segment:
    return Segment(
        id="s0001",
        index=0,
        speaker_id=1,
        role=SpeakerRole.BUYER,
        start_ms=start,
        end_ms=end,
        text=text,
    )


# --------------------------------------------------------------------------
# Sentence boundaries
# --------------------------------------------------------------------------


class TestUrduSentenceSplitting:
    def test_urdu_full_stop_ends_a_sentence(self):
        # U+06D4 ARABIC FULL STOP, not "."
        text = "ہم دو ہفتوں میں تعیناتی کر سکتے ہیں۔ اس کے بعد تربیت ہوگی۔"
        assert len(split_sentences(text)) == 2

    def test_urdu_question_mark_ends_a_sentence(self):
        # U+061F ARABIC QUESTION MARK, not "?"
        text = "آپ کا بجٹ کیا ہے؟ اور فیصلہ کون کرتا ہے؟"
        assert len(split_sentences(text)) == 2

    def test_english_splitting_is_unchanged(self):
        text = "We can deploy in two weeks. Training follows. Is that workable?"
        assert len(split_sentences(text)) == 3


# --------------------------------------------------------------------------
# Questions
# --------------------------------------------------------------------------


class TestUrduQuestions:
    @pytest.mark.parametrize(
        "text",
        [
            "کیا آپ کے پاس بجٹ منظور ہو چکا ہے؟",          # do you have budget approved?
            "آپ کا بجٹ کیا ہے؟",                            # what is your budget?
            "یہ فیصلہ کون کرتا ہے؟",                        # who makes this decision?
            "آپ ابھی رینیوَل کیسے سنبھالتے ہیں؟",           # how do you handle renewals?
        ],
    )
    def test_punctuated_urdu_questions(self, text):
        assert is_question(text)

    @pytest.mark.parametrize(
        "text",
        [
            # ASR routinely drops the mark; the interrogative still carries it.
            "یہ فیصلہ کون کرتا ہے",                         # who decides this
            "آپ ابھی رینیوَل کیسے سنبھالتے ہیں",            # how do you handle renewals
            "اس میں سب سے زیادہ وقت کہاں لگتا ہے",          # where does the time go
            "آپ نے یہ کب شروع کیا",                         # when did you start this
            "کیا آپ اگلے ہفتے دستیاب ہیں",                  # are you free next week
        ],
    )
    def test_unpunctuated_urdu_questions(self, text):
        assert is_question(text)

    @pytest.mark.parametrize(
        "text",
        [
            "ہم دو ہفتوں میں تعیناتی کر سکتے ہیں۔",         # we can deploy in two weeks
            "میں نے یہ کام کل کیا۔",                        # I did this work yesterday
            "قیمت ہمارے بجٹ سے زیادہ ہے۔",                  # the price is above our budget
        ],
    )
    def test_urdu_statements_are_not_questions(self, text):
        assert not is_question(text)

    def test_the_verb_kiya_is_not_the_interrogative_kya(self):
        """"کیا" is both "what" and the past participle of "to do".

        Counting the verb as a question would inflate a rep's question rate,
        and for a coaching product a false positive is worse than a miss.
        """
        assert not is_question("میں نے کام کیا۔")


class TestRomanUrduQuestions:
    @pytest.mark.parametrize(
        "text",
        [
            "Kya aap ke paas budget approved hai?",
            "Aap ka budget kitna hai?",
            "Ye decision kaun karta hai?",
            "Abhi legal par deal atakti hai to kya hota hai?",
        ],
    )
    def test_punctuated(self, text):
        assert is_question(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Ye decision kaun karta hai",
            "Aap renewals kaise handle karte hain",
            "Is mein sab se zyada waqt kahan lagta hai",
        ],
    )
    def test_unpunctuated(self, text):
        assert is_question(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Hum do hafton mein deploy kar sakte hain.",
            "Price hamare budget se zyada hai.",
        ],
    )
    def test_statements(self, text):
        assert not is_question(text)


class TestOpenVersusClosed:
    @pytest.mark.parametrize(
        "text",
        [
            "کیا ہوتا ہے جب ڈیل رک جاتی ہے؟",       # what happens when a deal stalls
            "آپ ابھی رینیوَل کیسے سنبھالتے ہیں؟",    # how do you handle renewals
            "یہ فیصلہ کون کرتا ہے؟",                 # who makes this decision
            "اس کی قیمت کتنی ہوگی؟",                 # how much will it cost
        ],
    )
    def test_urdu_open(self, text):
        assert is_open_question(text)

    @pytest.mark.parametrize(
        "text",
        [
            "کیا آپ کے پاس بجٹ ہے؟",                # do you have budget
            "کیا آپ اگلے ہفتے دستیاب ہیں؟",         # are you free next week
            "کیا یہ آپ کے لیے کام کرے گا؟",          # will this work for you
        ],
    )
    def test_urdu_closed(self, text):
        """Sentence-initial "کیا" followed by a subject is the yes/no marker."""
        assert is_question(text)
        assert not is_open_question(text)

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Kya hota hai jab deal ruk jati hai?", True),   # what happens
            ("Aap ka process kya hai?", True),               # what is your process
            ("Kaise handle karte hain aap?", True),          # how do you handle it
            ("Kya aap ke paas budget hai?", False),          # do you have budget
            ("Kya aap available hain?", False),              # are you available
        ],
    )
    def test_roman_open_versus_closed(self, text, expected):
        assert is_question(text)
        assert is_open_question(text) is expected

    def test_english_open_and_closed_unchanged(self):
        assert is_open_question("What happens when a deal stalls?")
        assert not is_open_question("Do you have budget approved?")


# --------------------------------------------------------------------------
# Backchannels
# --------------------------------------------------------------------------


class TestUrduBackchannels:
    @pytest.mark.parametrize(
        "text",
        ["جی", "جی جی", "جی ہاں", "اچھا", "ٹھیک ہے", "بالکل", "اچھا اچھا"],
    )
    def test_urdu_acknowledgements(self, text):
        """These must not count as taking the floor.

        Before the tokeniser was made Unicode-aware it found zero words in
        Urdu, so every one of these ended a rep's monologue — which quietly
        made longest-monologue meaningless on an Urdu call.
        """
        assert is_backchannel(seg(text))

    @pytest.mark.parametrize("text", ["ji", "ji haan", "acha", "theek hai", "bilkul"])
    def test_roman_acknowledgements(self, text):
        assert is_backchannel(seg(text))

    def test_a_short_substantive_urdu_turn_is_not_a_backchannel(self):
        assert not is_backchannel(seg("قیمت زیادہ ہے"))  # the price is high

    def test_a_long_acknowledgement_is_not_a_backchannel(self):
        # Past BACKCHANNEL_MAX_MS: if it took two seconds it was a turn.
        assert not is_backchannel(seg("جی ہاں", start=0, end=2_500))

    def test_english_backchannels_unchanged(self):
        assert is_backchannel(seg("mm-hmm"))
        assert is_backchannel(seg("right, yeah"))
        assert not is_backchannel(seg("that is too expensive"))


# --------------------------------------------------------------------------
# Fillers
# --------------------------------------------------------------------------


class TestUrduFillers:
    def test_urdu_discourse_fillers_are_counted(self):
        # "yaani" and "matlab" are the exact analogues of "I mean".
        assert count_fillers("یعنی مطلب ہم اسے اگلے ہفتے بھیج دیتے ہیں") == 2

    def test_roman_urdu_fillers_are_counted(self):
        assert count_fillers("matlab yaani hum ise ship kar dete hain") == 2

    def test_code_switched_fillers_are_counted_once_each(self):
        # One English, one Roman Urdu, in the same sentence.
        assert count_fillers("basically matlab we can ship it") == 2

    def test_clean_urdu_has_no_fillers(self):
        assert count_fillers("ہم اسے اگلے ہفتے بھیج دیں گے") == 0

    def test_english_filler_counting_unchanged(self):
        assert count_fillers("um, so like, you know, we uh ship it") == 3


# --------------------------------------------------------------------------
# The measurement this was all for
# --------------------------------------------------------------------------


class TestUrduCallMeasuresLikeAnEnglishOne:
    def test_a_discovery_call_in_urdu_counts_its_questions(self):
        """The regression that started this: four questions, zero counted.

        A rep running textbook discovery in Urdu was measured as though they
        had asked nothing, which put them at the bottom of the leaderboard for
        speaking their own language.
        """
        turns = [
            "السلام علیکم، آج وقت دینے کا شکریہ۔",             # statement
            "کیا آپ بتا سکتے ہیں کہ آپ کی ٹیم رینیوَل کیسے سنبھالتی ہے؟",
            "اس میں سب سے زیادہ وقت کہاں لگتا ہے؟",
            "اگر یہ اگلے کوارٹر تک ایسے ہی چلے تو اس کی قیمت کیا ہوگی؟",
            "کیا ہم اگلے ہفتے آپ کی فنانس ٹیم کے ساتھ بیٹھ سکتے ہیں؟",
        ]
        assert [is_question(t) for t in turns] == [False, True, True, True, True]

    def test_open_and_closed_are_distinguished_in_urdu(self):
        turns = [
            "اس میں سب سے زیادہ وقت کہاں لگتا ہے؟",            # where -> open
            "کیا ہم اگلے ہفتے بیٹھ سکتے ہیں؟",                  # yes/no -> closed
        ]
        assert [is_open_question(t) for t in turns] == [True, False]


# --------------------------------------------------------------------------
# Spoken sentence shape
#
# These are English cases, found by running one identical call through the
# engine twice -- once in English, once in Urdu -- and asking why the two
# disagreed. The Urdu path searched the whole sentence and got them right;
# the English path matched only on the prefix and got them wrong.
# --------------------------------------------------------------------------


class TestSpokenSentenceShape:
    @pytest.mark.parametrize(
        "text",
        [
            "And what does that cost you?",
            "So how are you handling renewals today?",
            "I mean, where does most of the time actually go?",
            "Well, why has this not moved since March?",
            "Okay, who signs this off?",
        ],
    )
    def test_a_discourse_marker_does_not_hide_an_open_question(self, text):
        """People do not speak in written sentences.

        A rep opening with "And" or "I mean" is asking the same question as a
        rep who does not, and scoring the second as discovery while scoring
        the first as nothing made the metric a measure of diction.
        """
        assert is_question(text)
        assert is_open_question(text)

    @pytest.mark.parametrize(
        "text",
        [
            "And if that runs another quarter, what does it cost you?",
            "If we did nothing, how much would that cost?",
            "Assuming legal signs off, when could you start?",
        ],
    )
    def test_a_conditional_clause_does_not_hide_an_open_question(self, text):
        """The interrogative is not always at the front, even in English."""
        assert is_question(text)
        assert is_open_question(text)

    def test_a_subordinate_what_is_not_a_question(self):
        """The clause rule is bounded by the comma, so this stays a statement."""
        assert not is_question("I know what you mean.")
        assert not is_open_question("I know what you mean.")

    def test_a_yes_no_question_stays_closed(self):
        assert is_question("Do you know what the budget is?")
        assert not is_open_question("Do you know what the budget is?")

    def test_stripping_never_empties_the_sentence(self):
        # Every token is a discourse marker; the sentence must survive.
        assert is_question("right?")
        assert not is_open_question("so")


# --------------------------------------------------------------------------
# Pace
#
# Words per minute is not comparable between languages. Urdu needs roughly a
# seventh more words to carry the same content, so a rep speaking it at an
# ordinary pace measures "faster" on a scale calibrated for English -- and was
# marked down for it, or flattered by it, depending on which side of the band
# the call happened to fall.
# --------------------------------------------------------------------------


class TestLanguageDetection:
    @pytest.mark.parametrize(
        "text",
        [
            "Thanks for the time. How does your team handle renewals right now?",
            "The budget for this quarter covers the Karachi and Lahore offices.",
            "Is the main issue in the north or is it across all of the regions?",
        ],
    )
    def test_english_stays_english(self, text):
        """Including English full of words that are also Roman Urdu.

        "the", "is", "us", "main" and "par" are Roman Urdu words too. Treating
        them as evidence classified a Pakistani rep speaking English as
        speaking Urdu, and scored them against the wrong pace band.
        """
        assert detect_language(text) == "en"

    @pytest.mark.parametrize(
        "text",
        [
            "\u0622\u062c \u0648\u0642\u062a \u062f\u06cc\u0646\u06d2 \u06a9\u0627 \u0634\u06a9\u0631\u06cc\u06c1\u06d4 \u0622\u067e \u06a9\u06cc \u0679\u06cc\u0645 \u0631\u06cc\u0646\u06cc\u0648\u064e\u0644 \u06a9\u06cc\u0633\u06d2 \u0633\u0646\u0628\u06be\u0627\u0644\u062a\u06cc \u06c1\u06d2\u061f",
            "\u06cc\u06c1 \u0627\u0633 \u0628\u062c\u0679 \u0633\u06d2 \u0632\u06cc\u0627\u062f\u06c1 \u06c1\u06d2 \u062c\u0648 \u06c1\u0645 \u0646\u06d2 \u0645\u0646\u0638\u0648\u0631 \u06a9\u06cc\u0627 \u062a\u06be\u0627\u06d4",
        ],
    )
    def test_urdu_script(self, text):
        assert detect_language(text) == "ur"

    @pytest.mark.parametrize(
        "text",
        [
            "Aaj waqt dene ka shukriya. Aap ki team renewals kaise sambhalti hai?",
            "Hum taqreeban do hafton mein deploy kar sakte hain, aur training bhi.",
            "Ye us budget se zyada hai jo hum ne manzoor kiya tha.",
        ],
    )
    def test_roman_urdu(self, text):
        assert detect_language(text) == "ur-roman"

    def test_empty_speech_defaults_to_english(self):
        assert detect_language("") == "en"
        assert detect_language("     ") == "en"

    def test_one_borrowed_word_is_not_a_change_of_language(self):
        assert detect_language("We shipped the pilot to Karachi last week.") == "en"


class TestPaceCalibration:
    def test_the_ratio_is_derived_from_the_corpus_not_asserted(self):
        """The number that decides the band has to be recomputable.

        Edit the parallel corpus and the bands move with it. That is the
        point: this is evidence, not a constant somebody once chose.
        """
        ratios = derive_ratios()
        assert ratios["en"] == 1.0
        assert 1.05 < ratios["ur"] < 1.30
        assert 1.05 < ratios["ur-roman"] < 1.30

    def test_the_urdu_band_spans_the_ratio_interval(self):
        """The band is an interval, not a point.

        Four independent estimates of the ratio disagree by more than the
        correction they are meant to make, so a single value cannot decide
        part of a score. The floor uses the low end of the interval and the
        ceiling the high end, which keeps the residual bounded in both
        directions instead of eliminating it in one and doubling it in the
        other.
        """
        lo_en, hi_en = B.wpm_band("en")
        lo_ur, hi_ur = B.wpm_band("ur")
        low_ratio, high_ratio = B.PACE_RATIO_BOUNDS["ur"]

        assert (lo_en, hi_en) == (B.WPM_TARGET_LOW, B.WPM_TARGET_HIGH)
        assert lo_ur > lo_en and hi_ur > hi_en
        assert lo_ur == pytest.approx(lo_en * low_ratio, abs=0.1)
        assert hi_ur == pytest.approx(hi_en * high_ratio, abs=0.1)
        # Wider than English, because it is known less precisely.
        assert (hi_ur - lo_ur) > (hi_en - lo_en)

    def test_the_interval_brackets_every_measured_estimate(self):
        """It has to contain the evidence, or it is not an interval.

        The corpus estimate is one of four; the bounds must sit either side of
        the cluster rather than tracking whichever was computed last.
        """
        low, high = B.PACE_RATIO_BOUNDS["ur"]
        assert low < derive_ratios()["ur"] < high

    def test_english_is_the_only_calibrated_language(self):
        """Everything else has a widened band until real recordings exist."""
        assert B.PACE_CALIBRATED == frozenset({"en"})

    def test_an_unknown_language_falls_back_to_english(self):
        assert B.wpm_band("fr") == (B.WPM_TARGET_LOW, B.WPM_TARGET_HIGH)


class TestPaceParityAcrossLanguages:
    """The same call in three languages should score the same on pace.

    These utterances are deliberately NOT the calibration corpus. A
    calibration that only works on its own training data is not a calibration.
    """

    SCRIPT = [
        (SpeakerRole.REP,
         "Thanks for making the time today. How does your team handle renewals right now?",
         "\u0622\u062c \u0648\u0642\u062a \u062f\u06cc\u0646\u06d2 \u06a9\u0627 \u0634\u06a9\u0631\u06cc\u06c1\u06d4 \u0622\u067e \u06a9\u06cc \u0679\u06cc\u0645 \u0627\u0628\u06be\u06cc \u0631\u06cc\u0646\u06cc\u0648\u064e\u0644 \u06a9\u06cc\u0633\u06d2 \u0633\u0646\u0628\u06be\u0627\u0644\u062a\u06cc \u06c1\u06d2\u061f",
         "Aaj waqt dene ka shukriya. Aap ki team abhi renewals kaise sambhalti hai?"),
        (SpeakerRole.BUYER,
         "It is spread across three account managers and a spreadsheet nobody owns.",
         "\u06cc\u06c1 \u062a\u06cc\u0646 \u0627\u06a9\u0627\u0624\u0646\u0679 \u0645\u06cc\u0646\u06cc\u062c\u0631\u0632 \u0627\u0648\u0631 \u0627\u06cc\u06a9 \u0634\u06cc\u0679 \u067e\u0631 \u067e\u06be\u06cc\u0644\u0627 \u06c1\u0648\u0627 \u06c1\u06d2 \u062c\u0633 \u06a9\u0627 \u06a9\u0648\u0626\u06cc \u0645\u0627\u0644\u06a9 \u0646\u06c1\u06cc\u06ba\u06d4",
         "Ye teen account managers aur ek sheet par phaila hua hai jis ka koi malik nahi."),
        (SpeakerRole.REP,
         "Where does most of the time actually go? And what does that cost you?",
         "\u0633\u0628 \u0633\u06d2 \u0632\u06cc\u0627\u062f\u06c1 \u0648\u0642\u062a \u06a9\u06c1\u0627\u06ba \u0644\u06af\u062a\u0627 \u06c1\u06d2\u061f \u0627\u0648\u0631 \u0627\u0633 \u06a9\u06cc \u0642\u06cc\u0645\u062a \u06a9\u06cc\u0627 \u06c1\u0648\u062a\u06cc \u06c1\u06d2\u061f",
         "Sab se zyada waqt kahan lagta hai? Aur is ki cost kya hoti hai?"),
        (SpeakerRole.REP,
         "We can deploy in about two weeks. Can we meet your finance team next week?",
         "\u06c1\u0645 \u062a\u0642\u0631\u06cc\u0628\u0627\u064b \u062f\u0648 \u06c1\u0641\u062a\u0648\u06ba \u0645\u06cc\u06ba \u062a\u0639\u06cc\u0646\u0627\u062a\u06cc \u06a9\u0631 \u0633\u06a9\u062a\u06d2 \u06c1\u06cc\u06ba\u06d4 \u06a9\u06cc\u0627 \u06c1\u0645 \u0627\u06af\u0644\u06d2 \u06c1\u0641\u062a\u06d2 \u0622\u067e \u06a9\u06cc \u0641\u0646\u0627\u0646\u0633 \u0679\u06cc\u0645 \u0633\u06d2 \u0645\u0644 \u0633\u06a9\u062a\u06d2 \u06c1\u06cc\u06ba\u061f",
         "Hum taqreeban do hafton mein deploy kar sakte hain. Kya hum agle hafte aap ki finance team se mil sakte hain?"),
    ]

    def _build(self, idx: int, wpm: float) -> Transcript:
        """Timings taken from the ENGLISH word count, so all three share a duration."""
        segs, t = [], 0
        for i, row in enumerate(self.SCRIPT):
            dur = int(len(row[1].split()) / wpm * 60_000)
            segs.append(
                Segment(id=f"s{i:04d}", index=i,
                        speaker_id=0 if row[0] is SpeakerRole.REP else 1,
                        role=row[0], start_ms=t, end_ms=t + dur, text=row[idx])
            )
            t += dur + 400
        return Transcript(call_id="c1", segments=segs)

    def _pace(self, idx: int, wpm: float) -> float:
        return score_pace(compute_metrics(self._build(idx, wpm))).score

    @pytest.mark.parametrize("wpm", [105.0, 125.0, 145.0, 157.0, 175.0, 195.0, 215.0])
    def test_a_rep_is_never_penalised_for_speaking_urdu(self, wpm):
        """The guarantee the pace axis actually makes.

        Four attempts to calibrate the Urdu word ratio gave 1.010, 1.116,
        1.137 and 1.154 — all from parallel text written for the purpose, so
        the spread measures the author's phrasing rather than the language,
        and it is wider than the correction it was meant to justify. Scoring
        on any single value left up to 15 points of bias, in whichever
        direction the call happened to fall.

        So delivery rate is credited in full where the band is an estimate.
        The consequence is asymmetric on purpose: an Urdu rep can never score
        *lower* than an English one delivering identically, at any speed.
        """
        english = self._pace(1, wpm)
        urdu = self._pace(2, wpm)
        roman = self._pace(3, wpm)
        assert urdu >= english, (wpm, english, urdu)
        assert roman >= english, (wpm, english, roman)

    @pytest.mark.parametrize("wpm", [145.0, 157.0, 175.0])
    def test_inside_the_english_band_the_scores_match_exactly(self, wpm):
        """Where English earns full marks on delivery, so does everyone."""
        assert self._pace(2, wpm) == self._pace(1, wpm)

    def test_the_leniency_is_bounded(self):
        """Crediting the term cannot be worth more than the term itself.

        The delivery-rate component carries 0.35 of a 0-100 axis weighted at
        0.12 overall, so the most this can ever be worth is about 4.2 points
        of overall score — and only to someone whose delivery we genuinely
        cannot judge.
        """
        worst = max(self._pace(2, w) - self._pace(1, w) for w in (105.0, 215.0))
        assert worst <= 35.0, worst

    def test_the_driver_says_the_rate_was_not_scored(self):
        """A number that did not count must not look like one that did."""
        m = compute_metrics(self._build(2, 200.0))
        assert m.language == "ur"
        driver = " ".join(score_pace(m).drivers)
        assert "not scored" in driver
        assert "not calibrated for Urdu" in driver
        # The measurement is still shown, because a manager should see it.
        assert str(m.rep_wpm) in driver

    def test_english_delivery_is_still_scored_and_judged(self):
        m = compute_metrics(self._build(1, 200.0))
        assert m.language == "en"
        driver = " ".join(score_pace(m).drivers)
        assert "not scored" not in driver
        assert "Spoke fast" in driver
