# -*- coding: utf-8 -*-
"""Question classification, held to the same standard in every language.

`is_question` and `is_open_question` used to be two functions with two
independent sets of rules, and they drifted: the second learned to split
clauses and the first did not, so a sentence could be "not a question" and
"an open question" simultaneously. Both now read from `classify_sentence`,
which makes that contradiction impossible rather than merely absent — and the
invariant is asserted here over every case in the file.

Each case carries its English gloss where it is not English, because every
expectation is a judgement about a language rather than about arithmetic.
"""

from __future__ import annotations

import pytest

from salix.metrics.engine import (
    classify_sentence,
    count_fillers,
    is_open_question,
    is_question,
)

# --------------------------------------------------------------------------
# The corpus. (expected, sentence) — shared by every test below.
# --------------------------------------------------------------------------

ENGLISH = [
    # --- open ---------------------------------------------------------
    ("open", "What happens when a deal stalls at legal?"),
    ("open", "How does your team handle renewals right now?"),
    ("open", "Walk me through what happens after legal signs off"),
    ("open", "Help me understand the approval path"),
    ("open", "Tell me more about the northern team"),
    # A discourse marker in front changes nothing about the question.
    ("open", "And what does that cost you?"),
    ("open", "I mean, where does most of the time actually go?"),
    ("open", "So talk me through the renewal process"),
    ("open", "Well, why has this not moved since March?"),
    # A conditional clause arrives before the interrogative -- with the comma
    # ASR usually drops, and without it.
    ("open", "If that runs another quarter, what does it cost you?"),
    ("open", "If we did nothing how much would that cost"),
    ("open", "Assuming legal signs off, when could you start?"),
    ("open", "Once the pilot ends how do you decide"),
    # Soft openers: discovery that never uses a wh-word.
    ("open", "Any thoughts on the timeline"),
    ("open", "Any concerns from the security side"),
    ("open", "What about the northern team"),
    ("open", "How about we start with a pilot"),
    # --- closed -------------------------------------------------------
    ("closed", "Do you have budget approved for this cycle?"),
    ("closed", "Can we sit with your finance team next week?"),
    ("closed", "Is that workable?"),
    ("closed", "Have you evaluated anything similar before?"),
    ("closed", "And do you have a date in mind?"),
    # Syntactically yes/no even though it contains a wh-word.
    ("closed", "Do you know what the budget is?"),
    # --- statements ---------------------------------------------------
    ("statement", "We can deploy in about two weeks."),
    ("statement", "You mentioned three managers earlier"),
    ("statement", "I understand the concern about migration."),
    ("statement", "The budget for this quarter covers both offices."),
    # A wh-word swallowed by a verb is not a question.
    ("statement", "I know what you mean."),
    ("statement", "Let me tell you how it works."),
    ("statement", "I never understood why they picked that vendor."),
]

URDU = [
    # --- open ---------------------------------------------------------
    ("open", "کیا ہوتا ہے جب ڈیل رک جاتی ہے؟"),            # what happens when a deal stalls
    ("open", "آپ ابھی رینیوَل کیسے سنبھالتے ہیں؟"),         # how do you handle renewals
    ("open", "یہ فیصلہ کون کرتا ہے"),                       # who makes this decision
    ("open", "اس میں سب سے زیادہ وقت کہاں لگتا ہے"),        # where does the time go
    ("open", "اس کی قیمت کتنی ہوگی؟"),                      # how much will it cost
    ("open", "اگر ہم کچھ نہ کریں تو اس کی قیمت کتنی ہوگی"),  # if we did nothing, how much
    ("open", "اس بارے میں آپ کی کیا رائے ہے"),              # what is your view on this
    ("open", "مجھے اس کے بارے میں مزید بتائیے"),            # tell me more about it
    ("open", "ذرا سمجھائیے کہ یہ کیسے چلتا ہے"),            # explain how this works
    # --- closed -------------------------------------------------------
    ("closed", "کیا آپ کے پاس بجٹ ہے؟"),                    # do you have budget
    ("closed", "کیا ہم اگلے ہفتے مل سکتے ہیں؟"),            # can we meet next week
    ("closed", "کیا یہ آپ کے لیے کام کرے گا؟"),             # will this work for you
    ("closed", "کیا آپ اگلے ہفتے دستیاب ہیں"),              # are you free next week
    # --- statements ---------------------------------------------------
    ("statement", "ہم دو ہفتوں میں تعیناتی کر سکتے ہیں۔"),   # we can deploy in two weeks
    ("statement", "قیمت ہمارے بجٹ سے زیادہ ہے۔"),            # the price is above our budget
    # "کیا" is also the past participle of "to do", and Urdu is verb-final.
    ("statement", "میں نے کام کیا۔"),                        # I did the work
    ("statement", "میں نے یہ کام کل کیا۔"),                  # I did this work yesterday
]

ROMAN_URDU = [
    ("open", "Aap ki team abhi renewals kaise sambhalti hai?"),
    ("open", "Ye decision kaun karta hai"),
    ("open", "Is mein sab se zyada waqt kahan lagta hai"),
    ("open", "Agar hum kuch na karen to is ki cost kitni hogi"),
    ("open", "Is baare mein aap ki kya raye hai"),
    ("open", "Mujhe is ke baare mein mazeed bataiye"),
    ("open", "Abhi legal par deal atakti hai to kya hota hai?"),
    ("closed", "Kya aap ke paas budget approved hai?"),
    ("closed", "Kya hum agle hafte mil sakte hain?"),
    ("statement", "Hum do hafton mein deploy kar sakte hain."),
    ("statement", "Price hamare budget se zyada hai."),
]

ALL = (
    [("english", e, t) for e, t in ENGLISH]
    + [("urdu", e, t) for e, t in URDU]
    + [("roman urdu", e, t) for e, t in ROMAN_URDU]
)


def _id(case):
    return f"{case[0]}-{case[1]}-{case[2][:28]}"


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------


class TestClassification:
    @pytest.mark.parametrize("case", ALL, ids=_id)
    def test_sentence_is_classified_correctly(self, case):
        language, expected, text = case
        assert classify_sentence(text) == expected, f"{language}: {text}"


class TestTheInvariant:
    """The contradiction that made this file necessary.

    A sentence must never be an open question without also being a question.
    Asserted over every case above rather than on a chosen example, so it
    cannot come back through a path nobody thought to test.
    """

    @pytest.mark.parametrize("case", ALL, ids=_id)
    def test_open_implies_question(self, case):
        _, _, text = case
        if is_open_question(text):
            assert is_question(text), text

    @pytest.mark.parametrize("case", ALL, ids=_id)
    def test_the_two_functions_agree_with_the_classifier(self, case):
        _, expected, text = case
        assert is_question(text) is (expected != "statement"), text
        assert is_open_question(text) is (expected == "open"), text

    @pytest.mark.parametrize("case", ALL, ids=_id)
    def test_a_question_mark_never_makes_something_a_statement(self, case):
        """Punctuation can only ever promote, never demote."""
        _, _, text = case
        marked = text.rstrip(".!?؟۔ ") + "?"
        assert is_question(marked), marked


class TestEveryLanguageIsCoveredEqually:
    """Guards against the file quietly becoming an English test again."""

    def test_each_language_has_open_closed_and_statement_cases(self):
        for name, cases in [
            ("english", ENGLISH),
            ("urdu", URDU),
            ("roman urdu", ROMAN_URDU),
        ]:
            kinds = {expected for expected, _ in cases}
            assert kinds == {"open", "closed", "statement"}, f"{name}: {kinds}"

    def test_no_language_is_a_token_afterthought(self):
        assert len(URDU) >= 12
        assert len(ROMAN_URDU) >= 10
        assert len(ENGLISH) >= 25


# --------------------------------------------------------------------------
# Fillers
# --------------------------------------------------------------------------


class TestFillers:
    @pytest.mark.parametrize(
        "expected,text",
        [
            (3, "um, so like, you know, we uh ship it"),
            (1, "basically that is the whole problem"),
            # A tag question is a tic whether or not the ASR kept the mark.
            (1, "We can ship it, right?"),
            (1, "That makes sense, right"),
            (1, "Does that make sense?"),
            (1, "Does that make sense"),
            # ... but "right" in the middle of a sentence is an ordinary word.
            (0, "The right approach is a pilot"),
            (0, "We picked the right team, honestly"),
            (0, "Right now the northern team is short-staffed"),
        ],
    )
    def test_english(self, expected, text):
        assert count_fillers(text) == expected, text

    @pytest.mark.parametrize(
        "expected,text",
        [
            (2, "یعنی مطلب ہم اسے اگلے ہفتے بھیج دیتے ہیں"),   # yaani, matlab
            (1, "دیکھیں یہ اتنا آسان نہیں ہے"),                # dekhen
            (0, "ہم اسے اگلے ہفتے بھیج دیں گے"),               # clean
        ],
    )
    def test_urdu(self, expected, text):
        assert count_fillers(text) == expected, text

    @pytest.mark.parametrize(
        "expected,text",
        [
            (2, "matlab yaani hum ise ship kar dete hain"),
            (1, "dekhen ye itna aasan nahi hai"),
            (0, "Hum ise agle hafte bhej den ge"),
        ],
    )
    def test_roman_urdu(self, expected, text):
        assert count_fillers(text) == expected, text

    def test_a_code_switched_sentence_counts_both(self):
        assert count_fillers("basically matlab we can ship it") == 2
