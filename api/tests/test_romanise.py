# -*- coding: utf-8 -*-
"""One script on the screen, and one the metrics engine can read.

Speech recognition returns Urdu as Nastaliq, or -- when asked for multilingual
-- as Devanagari, which is Hindi's script. The product writes both its
languages in Latin letters, so a transcript is transliterated before anything
measures it.

The valuable tests here are the refusals. A transliteration that comes back one
line short is worse than no transliteration at all: these lines are about to be
aligned with timestamps taken from the audio, so every word after the gap would
be attributed to the wrong moment and possibly the wrong speaker. Better to keep
the original script, which measures correctly and merely looks inconsistent.
"""

from __future__ import annotations

import pytest

from salix.pipeline.romanise import (
    NON_LATIN,
    _parse,
    needs_romanising,
    romanise,
)
from salix.providers.base import ASRSentence

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _sentences(*texts):
    return [
        ASRSentence(begin_time=i * 1000, end_time=i * 1000 + 900, text=t, speaker_id=i % 2)
        for i, t in enumerate(texts)
    ]


class _Providers:
    """Stands in for the provider graph with a scripted model reply."""

    def __init__(self, reply, fail=False):
        outer = self

        class _LLM:
            name = "fake"

            async def complete(self, **kwargs):
                if fail:
                    raise RuntimeError("model unavailable")
                outer.seen = kwargs
                return reply

        self.llm = _LLM()
        self.seen = {}


class TestDetection:
    def test_nastaliq_is_detected(self):
        assert needs_romanising(_sentences("آپ کی قیمت زیادہ ہے"))

    def test_devanagari_is_detected(self):
        """The worse case: `detect_language` reads this as English, so an Urdu
        call would be scored against English pace benchmarks."""
        assert needs_romanising(_sentences("आपका वक़्त देने का शुक्रिया"))

    def test_roman_urdu_is_left_alone(self):
        assert not needs_romanising(_sentences("Aap ki price bohat zyada hai"))

    def test_english_is_left_alone(self):
        assert not needs_romanising(_sentences("Thanks for making the time today."))

    async def test_a_latin_transcript_costs_no_model_call(self):
        providers = _Providers("should never be used")
        sentences = _sentences("Thanks for the time.", "It is mostly manual.")

        out, changed = await romanise(providers, sentences)

        assert changed is False
        assert out is sentences
        assert providers.seen == {}


class TestParsing:
    def test_a_well_formed_reply_is_read_back(self):
        assert _parse("1. Aap ka waqt\n2. Shukriya", 2) == ["Aap ka waqt", "Shukriya"]

    def test_a_short_reply_is_refused(self):
        """One line missing would shift every timestamp after it."""
        assert _parse("1. Aap ka waqt", 2) is None

    def test_a_long_reply_is_refused(self):
        assert _parse("1. a\n2. b\n3. c", 2) is None

    def test_a_reply_still_in_urdu_script_is_refused(self):
        """The model acknowledged the instruction and ignored it."""
        assert _parse("1. Aap ka waqt\n2. آپ کی قیمت", 2) is None

    def test_commentary_around_the_lines_is_ignored(self):
        reply = "Here you go:\n\n1. Aap ka waqt\n2. Shukriya\n\nHope that helps."
        assert _parse(reply, 2) == ["Aap ka waqt", "Shukriya"]

    def test_an_empty_line_is_not_accepted_as_content(self):
        assert _parse("1. Aap ka waqt\n2. ", 2) is None

    def test_a_closing_paren_is_accepted_as_numbering(self):
        assert _parse("1) one\n2) two", 2) == ["one", "two"]


class TestRomanising:
    async def test_text_is_replaced_and_timings_are_not(self):
        sentences = _sentences("آپ کا شکریہ", "قیمت زیادہ ہے")
        providers = _Providers("1. Aap ka shukriya\n2. Price zyada hai")

        out, changed = await romanise(providers, sentences)

        assert changed is True
        assert [s.text for s in out] == ["Aap ka shukriya", "Price zyada hai"]
        # The numbers every floor-control metric is computed from.
        assert [s.begin_time for s in out] == [s.begin_time for s in sentences]
        assert [s.end_time for s in out] == [s.end_time for s in sentences]
        assert [s.speaker_id for s in out] == [s.speaker_id for s in sentences]

    async def test_a_refused_reply_keeps_the_original(self):
        """Nastaliq measures correctly. A misaligned transcript does not."""
        sentences = _sentences("آپ کا شکریہ", "قیمت زیادہ ہے")
        providers = _Providers("1. Aap ka shukriya")  # one line short

        out, changed = await romanise(providers, sentences)

        assert changed is False
        assert [s.text for s in out] == ["آپ کا شکریہ", "قیمت زیادہ ہے"]

    async def test_a_model_failure_keeps_the_original(self):
        sentences = _sentences("آپ کا شکریہ")
        out, changed = await romanise(_Providers("", fail=True), sentences)

        assert changed is False
        assert out[0].text == "آپ کا شکریہ"

    async def test_devanagari_is_converted_too(self):
        sentences = _sentences("आपका वक़्त देने का शुक्रिया")
        providers = _Providers("1. Aap ka waqt dene ka shukriya")

        out, changed = await romanise(providers, sentences)

        assert changed is True
        assert not NON_LATIN.search(out[0].text)

    async def test_the_instruction_forbids_translating(self):
        """"shukriya", never "thank you" -- this is transliteration."""
        providers = _Providers("1. Aap ka shukriya")
        await romanise(providers, _sentences("آپ کا شکریہ"))

        system = providers.seen.get("system", "")
        assert "do not translate" in system.lower()
        assert "shukriya" in system

    async def test_it_asks_for_determinism(self):
        """Transliteration has a right answer; sampling it is pointless."""
        providers = _Providers("1. Aap ka shukriya")
        await romanise(providers, _sentences("آپ کا شکریہ"))

        assert providers.seen.get("temperature") == 0.0

    async def test_an_empty_transcript_is_handled(self):
        out, changed = await romanise(_Providers("x"), [])
        assert (out, changed) == ([], False)


class TestDownstream:
    async def test_the_result_is_detected_as_roman_urdu(self):
        """The point of the whole exercise.

        Nastaliq detects as `ur` and Devanagari as `en` -- the second silently
        applying English pace benchmarks to an Urdu call. Roman Urdu detects as
        `ur-roman`, which is the path the engine has calibrated benchmarks and
        interrogative lists for.
        """
        from salix.metrics.engine import detect_language

        providers = _Providers(
            "1. Aap ka waqt dene ka shukriya\n"
            "2. Zyada tar kaam haath se hota hai\n"
            "3. Aap ki price hamare budget se kaafi zyada hai"
        )
        sentences = _sentences(
            "آپ کا وقت دینے کا شکریہ",
            "زیادہ تر کام ہاتھ سے ہوتا ہے",
            "آپ کی قیمت ہمارے بجٹ سے کافی زیادہ ہے",
        )

        out, _ = await romanise(providers, sentences)
        joined = " ".join(s.text for s in out)

        assert detect_language(joined) == "ur-roman"

    def test_devanagari_is_why_this_exists(self):
        """Stated as a fact about the engine, so the reason is not forgotten."""
        from salix.metrics.engine import detect_language

        assert detect_language("आपका वक़्त देने का शुक्रिया. Renewal process") == "en"
        assert detect_language("آپ کا وقت دینے کا شکریہ") == "ur"
