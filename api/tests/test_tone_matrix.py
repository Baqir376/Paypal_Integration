# -*- coding: utf-8 -*-
"""Tone and register, across both languages, without spending a model call.

`scripts/tone_matrix.py` puts sixteen scenarios through the live model in both
languages. It is the real check and it costs one request per scenario, so it
runs when somebody asks rather than on every push.

This is the half that can be settled by arithmetic and string handling, and it
is the half most likely to rot quietly:

  * **Language detection** across tone. A furious rep, a rep typing in
    lowercase with no punctuation, and a rep switching languages mid-sentence
    must all be classified correctly. Get this wrong and the call is scored
    against the wrong benchmarks with nothing to indicate it.
  * **Objection vocabulary** across phrasing. People decline to change in a
    hundred ways and the detector knows a list. That list has already been
    wrong once, in the worst way -- "works" was in it and "worked" was not, so
    a buyer who refused four times was heard zero times.
  * **The measurements** under input nobody plans for: emoji, punctuation only,
    a single word, a paragraph, numerals, mixed script.
  * **The live harness's own rules.** Its checks are regexes, and a regex that
    quietly stops matching turns a red run green.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from salix.dojo.engine import _mentions_category
from salix.metrics.engine import compute_metrics, detect_language, is_question
from salix.providers.edge_voice import voice_for
from salix.schemas.call import Segment, Transcript
from salix.schemas.common import SpeakerRole

# The harness lives beside the app rather than in the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.tone_matrix import (  # noqa: E402
    BROKE_CHARACTER,
    FALLBACK,
    MASCULINE_SELF,
    NARRATION,
    NASTALIQ_OR_DEVANAGARI,
    SCENARIOS,
    Scenario,
    evaluate,
)


# --------------------------------------------------------------------------
# What people actually type, in every mood
# --------------------------------------------------------------------------

ENGLISH_BY_TONE = {
    "angry": "I have told two of your people this already and nobody listens.",
    "aggressive": "This is a waste of my time. Give me one reason not to hang up.",
    "frustrated": "We have been round this three times and I still have no answer.",
    "casual": "hey so whats the deal with this thing my boss wanted me to look",
    "friendly": "Honestly this looks great, I am quite excited about it.",
    "sceptical": "Every vendor says exactly this. What makes you different?",
    "evasive": "Yeah, maybe. Send me something and I will take a look.",
    "rushed": "I have four minutes. Skip the intro and tell me the cost.",
    "clipped": "ok",
    "formal": "I would be grateful if you could clarify the commercial terms.",
}

ROMAN_URDU_BY_TONE = {
    "angry": "Main aap ke do bandon ko yeh pehle bata chuka hoon aur koi sunta hi nahi.",
    "aggressive": "Yeh mera waqt zaya kar raha hai, mujhe ek wajah dein.",
    "frustrated": "Hum is par teen baar baat kar chuke hain aur jawab abhi tak nahi mila.",
    "casual": "haan to yeh cheez kya hai mere boss ne kaha tha dekh lo zara",
    "friendly": "Sach kahoon to yeh bohat acha lag raha hai, main kaafi khush hoon.",
    "sceptical": "Har vendor bilkul yehi kehta hai, aap kaise mukhtalif hain?",
    "evasive": "Haan dekhte hain, kuch bhej dein waqt mila to dekh loon ga.",
    "rushed": "Mere paas chaar minute hain, seedha batayein kitne ka hai.",
    "clipped": "theek hai",
    "formal": "Baraye meherbani commercial terms ki wazahat farma dein.",
}


class TestLanguageAcrossTone:
    """A rep's mood must not change which language they are speaking.

    Roman Urdu is Latin script, so the classifier works on vocabulary density
    rather than characters. Short and angry input is where that is thinnest.
    """

    @pytest.mark.parametrize("tone,text", sorted(ENGLISH_BY_TONE.items()))
    def test_english_stays_english(self, tone, text):
        assert detect_language(text) == "en", tone

    @pytest.mark.parametrize("tone,text", sorted(ROMAN_URDU_BY_TONE.items()))
    def test_roman_urdu_is_recognised(self, tone, text):
        # "theek hai" alone is two words; the detector is allowed to be unsure
        # on input that short, but must never call it something else confidently.
        assert detect_language(text) in {"ur-roman", "en"}, tone

    @pytest.mark.parametrize("tone", sorted(ROMAN_URDU_BY_TONE))
    def test_a_full_sentence_of_roman_urdu_is_never_missed(self, tone):
        if tone == "clipped":
            pytest.skip("two words carries no density signal either way")
        assert detect_language(ROMAN_URDU_BY_TONE[tone]) == "ur-roman"

    def test_code_switching_is_not_mistaken_for_english(self):
        """The normal register on a Pakistani floor, and the case a
        vocabulary-density test is most likely to get wrong."""
        text = ("Dekhein, our pricing is competitive kyunke value zyada hai, "
                "lekin main samajh raha hoon ke budget tight hai.")
        assert detect_language(text) == "ur-roman"

    def test_urdu_script_is_still_recognised(self):
        """Uploads can arrive in Nastaliq even though the Dojo cannot."""
        assert detect_language("آپ کی قیمت ہمارے بجٹ سے کافی زیادہ ہے") == "ur"


class TestObjectionVocabularyAcrossPhrasing:
    """The detector knows a list, and people do not.

    Every phrase here is one somebody would actually say. The list was wrong
    once in exactly this way: it held "works" and the buyer said "worked".
    """

    STATUS_QUO = [
        "it works well enough for us",
        "it has worked well enough so far",
        "honestly it is working fine",
        "nothing is really broken",
        "it isn't really broken",
        "we have already got a rhythm",
        "I am not looking to overhaul our process",
        "we are keeping our heads above water",
        "there is no need to change anything",
        "we are happy with what we have",
        "humara system theek chal raha hai",
        "team ko iski aadat ho chuki hai",
        "abhi koi masla nahi hai",
        "kaam nikal raha hai",
    ]

    PRICE = [
        "the price is well above our budget",
        "that is more than we were expecting to spend",
        "it is too expensive for a tool like this",
        "I cannot justify that kind of spend",
        "what does this actually cost",
        "the quote I saw was quite steep",
        "aap ki qeemat hamare budget se zyada hai",
        "yeh kaafi mehnga hai",
        "itna kharcha justify karna mushkil hai",
    ]

    @pytest.mark.parametrize("text", STATUS_QUO)
    def test_status_quo_is_heard(self, text):
        assert _mentions_category(text, "status_quo"), text

    @pytest.mark.parametrize("text", PRICE)
    def test_price_is_heard(self, text):
        assert _mentions_category(text, "price"), text

    @pytest.mark.parametrize(
        "text",
        ["how many people are on the team",
         "what does your renewal process look like",
         "who else would be involved in the decision"],
    )
    def test_an_unrelated_question_is_not_a_price_objection(self, text):
        """False positives credit a rep for work they did not do, which is the
        worse error: a wrong low score annoys, a wrong high score misleads."""
        assert not _mentions_category(text, "price"), text


class TestQuestionsAcrossTone:
    """Dictation produces no question marks, so tone must not decide this."""

    @pytest.mark.parametrize(
        "text",
        [
            "what is actually breaking in your process today",
            "how many hours a week does that take",
            "which number does your leadership care about",
            "who else needs to sign off on this",
            "reporting mein team ka kitna waqt jata hai",
            "aap ki team us se kya karti",
            "kaun sa number sab se zyada maayne rakhta hai",
            "yeh kaise chalta hai",
        ],
    )
    def test_a_question_without_a_question_mark(self, text):
        assert is_question(text), text

    @pytest.mark.parametrize(
        "text",
        [
            "our platform saves your team a lot of time",
            "do not worry most teams see value quickly",
            "fikar na karein sab ko jaldi value mil jati hai",
            "hamara platform bohat acha hai",
        ],
    )
    def test_a_statement_is_not_a_question(self, text):
        assert not is_question(text), text


class TestVoiceAcrossTone:
    """The buyer is a woman in every mood and both languages."""

    @pytest.mark.parametrize("tone,text", sorted(ROMAN_URDU_BY_TONE.items()))
    def test_roman_urdu_gets_the_indian_english_voice(self, tone, text):
        assert voice_for(text, "ur-roman") == "en-IN-NeerjaNeural", tone

    @pytest.mark.parametrize("tone,text", sorted(ENGLISH_BY_TONE.items()))
    def test_english_gets_the_british_voice(self, tone, text):
        assert voice_for(text, "en") == "en-GB-SoniaNeural", tone

    def test_no_tone_can_produce_a_male_voice(self):
        for text in list(ENGLISH_BY_TONE.values()) + list(ROMAN_URDU_BY_TONE.values()):
            for language in ("en", "ur-roman", "en-PK", "roman", ""):
                voice = voice_for(text, language)
                assert not any(n in voice for n in ("Asad", "Prabhat", "Ryan")), voice


class TestMeasurementUnderHostileInput:
    """Text that arrives from real people and breaks naive code."""

    def _transcript(self, *texts):
        segments = [
            Segment(
                id=f"s{i}", index=i,
                speaker_id=i % 2,
                role=SpeakerRole.REP if i % 2 == 0 else SpeakerRole.BUYER,
                start_ms=i * 5000, end_ms=i * 5000 + 4000, text=t,
            )
            for i, t in enumerate(texts)
        ]
        return Transcript(call_id="c", segments=segments)

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "???",
            "...",
            "ok",
            "👍",
            "😡😡😡 this is unacceptable",
            "£1,400 a month at 45 dollars an hour",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "Dekhein, our price is fine kyunke value zyada hai",
            "آپ کی قیمت زیادہ ہے",
            "आपका वक़्त देने का शुक्रिया",
            "a" * 5000,
        ],
    )
    def test_nothing_raises_and_the_invariants_hold(self, text):
        m = compute_metrics(self._transcript(text, "and a reply"), 12_000)
        assert 0.0 <= m.talk_ratio_rep <= 1.0
        assert m.silence_ms >= 0
        assert m.rep_wpm >= 0
        assert m.rep_question_count >= 0

    def test_numerals_survive_into_the_transcript(self):
        """A rep quoting 1,400 dollars must not have it silently reshaped."""
        transcript = self._transcript("That is roughly 1,400 dollars a month.")
        assert "1,400" in transcript.segments[0].text


class TestTheHarnessChecksItself:
    """The live harness judges by regex, and a regex that stops matching turns
    a red run green. These are the rules that produced a false 16/16."""

    def test_the_fallback_is_recognised(self):
        assert FALLBACK == "sorry, could you say that again?"
        checks = evaluate(Scenario("x", "x", "", ""), "en", "", "Sorry, could you say that again?")
        assert checks["not a fallback"] is False

    def test_a_real_reply_is_not_mistaken_for_the_fallback(self):
        checks = evaluate(Scenario("x", "x", "", ""), "en", "", "Look, I have heard that before.")
        assert checks["not a fallback"] is True

    @pytest.mark.parametrize(
        "reply",
        ["As an AI language model, I cannot do that.",
         "I'm an AI assistant playing a persona.",
         "Let us continue this roleplay.",
         "Main ek AI hoon."],
    )
    def test_breaking_character_is_caught(self, reply):
        assert BROKE_CHARACTER.search(reply), reply

    @pytest.mark.parametrize(
        "reply",
        ["Look, I have heard that pitch before and it never lands.",
         "Dekhein, main abhi is ki zaroorat nahi samajhti.",
         "That is a fair question, but my leadership cares about retention."],
    )
    def test_a_buyer_in_character_is_not_flagged(self, reply):
        assert not BROKE_CHARACTER.search(reply), reply

    def test_narration_is_caught(self):
        assert NARRATION.search("*leans back* I am not convinced.")
        assert NARRATION.search("(laughs) no thanks")
        assert not NARRATION.search("I am not convinced by that at all.")

    def test_the_script_rule_catches_both_wrong_scripts(self):
        assert NASTALIQ_OR_DEVANAGARI.search("آپ کی قیمت")
        assert NASTALIQ_OR_DEVANAGARI.search("आपका वक़्त")
        assert not NASTALIQ_OR_DEVANAGARI.search("Aap ki qeemat zyada hai")

    def test_masculine_self_reference_is_caught(self):
        assert MASCULINE_SELF.search("main yeh kar raha hoon")
        assert not MASCULINE_SELF.search("main yeh kar rahi hoon")
        # "hum ... rahe hain" is plural and correct; it must not trip.
        assert not MASCULINE_SELF.search("hum yeh kar rahe hain")

    def test_a_roman_urdu_reply_in_nastaliq_fails_the_script_check(self):
        checks = evaluate(Scenario("x", "x", "", ""), "ur-roman", "", "آپ کی قیمت زیادہ ہے")
        assert checks["script"] is False

    def test_the_same_reply_passes_in_an_english_session(self):
        """The rule is about the session's language, not about the characters
        being forbidden everywhere -- an upload may legitimately be Nastaliq."""
        checks = evaluate(Scenario("x", "x", "", ""), "en", "", "آپ کی قیمت زیادہ ہے")
        assert checks["script"] is True

    def test_every_scenario_carries_both_languages(self):
        for scenario in SCENARIOS:
            assert scenario.en.strip(), scenario.id
            assert scenario.ur.strip(), scenario.id

    def test_the_matrix_covers_the_tones_that_were_asked_for(self):
        ids = {s.id for s in SCENARIOS}
        for required in ("angry", "aggressive", "frustrated", "casual",
                         "friendly", "sceptical", "evasive", "rushed",
                         "monosyllabic", "reassurance", "profane",
                         "code_switch", "jailbreak", "off_topic",
                         "wall_of_text", "numbers"):
            assert required in ids, required
