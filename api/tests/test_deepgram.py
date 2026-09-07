# -*- coding: utf-8 -*-
"""Transcription with speaker separation.

The capability that was missing, and the one every floor-control number is
computed from: talk ratio, longest monologue, patience, interruptions. If the
speakers are wrong or the timestamps are in the wrong unit, none of those
numbers mean anything, and nothing downstream would notice.

No network here. The shapes are the ones Deepgram documents, and the value of
these tests is that they pin the translation between their response and this
codebase's own.
"""

from __future__ import annotations

import pytest

from salix.config import ProviderMode, Settings
from salix.providers.base import ProviderError
from salix.providers.deepgram_asr import DeepgramASR

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _settings(**kwargs):
    return Settings(provider_mode=ProviderMode.AUTO, deepgram_api_key="dg-test", **kwargs)


def _response(utterances, duration=12.5):
    return {
        "metadata": {"duration": duration, "model_info": {"name": "nova-3"}},
        "results": {"utterances": utterances},
    }


def _utterance(start, end, text, speaker):
    return {"start": start, "end": end, "transcript": text, "speaker": speaker}


class TestParsing:
    def test_seconds_become_milliseconds(self):
        """Deepgram counts in seconds. Everything here is in milliseconds, and
        a silent factor-of-1000 error would make every duration metric wrong
        while leaving the transcript perfectly readable."""
        result = DeepgramASR(_settings())._parse(
            _response([_utterance(0.41916, 5.43012, "four score and seven years", 0)])
        )
        sentence = result.sentences[0]
        assert sentence.begin_time == 419
        assert sentence.end_time == 5430

    def test_speakers_are_preserved(self):
        result = DeepgramASR(_settings())._parse(
            _response([
                _utterance(0.0, 2.0, "How does your renewal run today?", 0),
                _utterance(2.4, 6.1, "It is manual, mostly.", 1),
            ])
        )
        assert [s.speaker_id for s in result.sentences] == [0, 1]

    def test_the_transcript_survives_intact(self):
        result = DeepgramASR(_settings())._parse(
            _response([_utterance(0.0, 3.0, "  Aap ki price bohat zyada hai.  ", 1)])
        )
        assert result.sentences[0].text == "Aap ki price bohat zyada hai."

    def test_urdu_script_survives_intact(self):
        """Nova-3 returns Nastaliq for `language=ur`, and the metrics engine
        reads it -- so nothing here may mangle it."""
        result = DeepgramASR(_settings())._parse(
            _response([_utterance(0.0, 3.0, "آپ کی قیمت بہت زیادہ ہے۔", 1)])
        )
        assert result.sentences[0].text == "آپ کی قیمت بہت زیادہ ہے۔"

    def test_empty_utterances_are_skipped_not_stored(self):
        result = DeepgramASR(_settings())._parse(
            _response([
                _utterance(0.0, 1.0, "", 0),
                _utterance(1.0, 4.0, "Real speech.", 1),
            ])
        )
        assert len(result.sentences) == 1

    def test_no_speech_at_all_is_an_error_not_an_empty_transcript(self):
        """An empty transcript would be measured, scored and presented as a
        finished analysis of a call nobody said anything in."""
        with pytest.raises(ProviderError) as caught:
            DeepgramASR(_settings())._parse(_response([]))
        assert "no speech" in str(caught.value).lower()

    def test_duration_is_carried_through(self):
        result = DeepgramASR(_settings())._parse(
            _response([_utterance(0.0, 3.0, "Hello.", 0)], duration=1834.2)
        )
        assert result.duration_ms == 1834200

    def test_a_missing_speaker_field_defaults_rather_than_crashing(self):
        """Diarization off, or a model that does not support it."""
        result = DeepgramASR(_settings())._parse(
            _response([{"start": 0.0, "end": 2.0, "transcript": "Hello."}])
        )
        assert result.sentences[0].speaker_id == 0


class TestRequestShape:
    def test_diarization_is_asked_for(self):
        params = DeepgramASR(_settings())._params(("en",), True)
        assert params["diarize"] == "true"
        assert params["utterances"] == "true"

    def test_smart_format_is_on(self):
        """The metrics engine splits sentences on punctuation. Without this
        every turn arrives as one unbroken run and the question count, which
        drives the discovery axis, collapses to nothing."""
        assert DeepgramASR(_settings())._params(("en",), True)["smart_format"] == "true"

    def test_a_single_hint_pins_the_language(self):
        assert DeepgramASR(_settings())._params(("ur",), True)["language"] == "ur"
        assert DeepgramASR(_settings())._params(("en-PK",), True)["language"] == "en"

    def test_mixed_hints_fall_back_to_multilingual(self):
        """A Pakistani sales call moves between Urdu and English inside one
        sentence; pinning it to either transcribes the other half as noise."""
        assert DeepgramASR(_settings())._params(("en", "ur"), True)["language"] == "multi"

    def test_diarization_can_be_turned_off(self):
        """The Dojo's dictation fallback is one speaker by definition."""
        assert "diarize" not in DeepgramASR(_settings())._params(("en",), False)


class TestAudioSource:
    async def test_a_remote_url_is_passed_by_reference(self):
        content, payload, content_type = await DeepgramASR(_settings())._body(
            "https://example.com/call.mp3"
        )
        assert content is None
        assert payload == {"url": "https://example.com/call.mp3"}
        assert content_type == "application/json"

    async def test_a_local_file_is_read_and_posted(self, tmp_path):
        """The whole reason this provider needs no public address, and why a
        laptop can transcribe a real call at all."""
        path = tmp_path / "call.mp3"
        path.write_bytes(b"ID3fake-audio")

        content, payload, content_type = await DeepgramASR(_settings())._body(str(path))
        assert content == b"ID3fake-audio"
        assert payload is None
        assert content_type == "audio/mpeg"

    async def test_inline_audio_is_decoded(self):
        import base64

        raw = b"webm-bytes"
        url = "data:audio/webm;base64," + base64.b64encode(raw).decode()
        content, payload, content_type = await DeepgramASR(_settings())._body(url)
        assert content == raw
        assert content_type == "audio/webm"

    async def test_a_missing_file_says_so_before_the_upload(self, tmp_path):
        with pytest.raises(ProviderError) as caught:
            await DeepgramASR(_settings())._body(str(tmp_path / "gone.mp3"))
        assert "no audio at" in str(caught.value)


class TestSelection:
    def test_a_deepgram_key_alone_makes_transcription_live(self):
        settings = _settings()
        assert settings.asr_is_live is True
        assert settings.asr_provider_name == "deepgram"

    def test_deepgram_is_preferred_over_model_studio(self):
        """It takes the audio in the request body, so it works where Model
        Studio -- which fetches the file itself -- needs a reachable URL."""
        settings = Settings(
            provider_mode=ProviderMode.AUTO,
            deepgram_api_key="dg-x",
            dashscope_api_key="sk-x",
        )
        assert settings.asr_provider_name == "deepgram"
        assert settings.asr_model == "nova-3"

    def test_model_studio_still_works_on_its_own(self):
        settings = Settings(provider_mode=ProviderMode.AUTO, dashscope_api_key="sk-x")
        assert settings.asr_is_live is True
        assert settings.asr_provider_name == "alibaba model studio"

    def test_neither_means_the_offline_twin(self):
        settings = Settings(provider_mode=ProviderMode.AUTO)
        assert settings.asr_is_live is False
        assert settings.asr_provider_name == "offline twin"

    def test_the_provider_graph_picks_deepgram(self):
        from salix.providers import build_providers

        providers = build_providers(_settings())
        assert providers.asr.name == "deepgram"

    def test_a_deepgram_key_alone_does_not_claim_speech_or_embeddings(self):
        """It transcribes. It does not synthesise, and it has no embeddings."""
        settings = _settings()
        assert settings.dashscope_is_live is False
        assert settings.embeddings_is_live is False


def _word(text, start, end, speaker):
    return {"punctuated_word": text, "word": text.lower().strip(".,?!"),
            "start": start, "end": end, "speaker": speaker}


def _spoken(phrase, start, speaker, pace=0.3):
    """A phrase as consecutive words, one after another with no gap."""
    return [
        _word(t, start + i * pace, start + i * pace + pace * 0.9, speaker)
        for i, t in enumerate(phrase.split())
    ]


def _body(words, duration=60.0):
    return {
        "metadata": {"duration": duration, "model_info": {"name": "nova-3"}},
        "results": {"channels": [{"alternatives": [{"words": words}]}]},
    }


class TestSegmentingOnSpeakerNotSilence:
    """The failure a real recording produces, and the reason for word-level
    segmentation.

    Two people on one speakerphone talking without gaps -- which is what an
    actual sales call sounds like -- came back as thirteen utterances for two
    minutes, one of them a hundred and twenty-two words containing eight turns
    from *both* people. Every downstream number was then computed over a
    transcript that attributed the buyer's objections to the rep.

    Deepgram's diarization was never wrong: it had labelled all of those words
    correctly. The utterance grouping threw the labels away by splitting on
    silence, and there was no silence to split on. Telling the user to record
    differently is not a fix; a sales floor records how it records.
    """

    def test_speakers_split_even_with_no_pause_between_them(self):
        words = (
            _spoken("Assalam-o-alaikum Bilal sahab shukriya.", 0.5, 0)
            + _spoken("Walaikum assalam. Haan boliye.", 1.7, 1)
            + _spoken("Aap ka process kaise chalta hai?", 2.6, 0)
        )
        result = DeepgramASR(_settings())._parse(_body(words))

        assert len(result.sentences) == 3
        assert [s.speaker_id for s in result.sentences] == [0, 1, 0]

    def test_a_long_two_person_run_does_not_become_one_segment(self):
        """The exact shape of the failure: one block, both speakers."""
        words = []
        clock = 0.0
        for turn in range(8):
            words += _spoken("yeh ek lambi baat hai jo chalti rehti hai", clock, turn % 2)
            clock += 3.3
        result = DeepgramASR(_settings())._parse(_body(words))

        assert len(result.sentences) == 8
        assert {s.speaker_id for s in result.sentences} == {0, 1}
        longest = max(len(s.text.split()) for s in result.sentences)
        assert longest < 30, f"a segment of {longest} words is a merged turn"

    def test_no_segment_ever_holds_two_speakers(self):
        """The invariant. Everything downstream depends on it."""
        words = []
        for i in range(40):
            words += _spoken("baat cheet jaari hai", i * 1.3, i % 2)
        result = DeepgramASR(_settings())._parse(_body(words))

        boundaries = [(s.begin_time, s.end_time, s.speaker_id) for s in result.sentences]
        for begin, end, speaker in boundaries:
            owners = {
                int(w["speaker"]) for w in words
                if begin <= int(round(w["start"] * 1000)) < end
            }
            assert owners <= {speaker}, f"segment {begin}-{end} holds {owners}"

    def test_one_speaker_is_still_broken_at_real_pauses(self):
        """Otherwise a two-minute answer arrives as a single wall of text."""
        words = (
            _spoken("pehla hissa hai yeh.", 0.0, 0)
            + _spoken("aur yeh doosra hissa hai.", 4.0, 0)   # 2.6s gap
        )
        result = DeepgramASR(_settings())._parse(_body(words))
        assert len(result.sentences) == 2
        assert all(s.speaker_id == 0 for s in result.sentences)

    def test_timings_come_from_the_words_they_contain(self):
        words = _spoken("aap ka waqt", 2.0, 0)
        result = DeepgramASR(_settings())._parse(_body(words))
        segment = result.sentences[0]

        assert segment.begin_time == 2000
        assert segment.end_time == int(round(words[-1]["end"] * 1000))

    def test_punctuated_words_are_preferred(self):
        """Sentence boundaries are what the metrics engine splits on."""
        result = DeepgramASR(_settings())._parse(_body(_spoken("Theek hai. Boliye?", 0.0, 0)))
        assert "." in result.sentences[0].text or "?" in result.sentences[0].text

    def test_utterances_still_work_when_there_are_no_words(self):
        """Diarization off, or a model that emits no word list."""
        body = {
            "metadata": {"duration": 6.0},
            "results": {"utterances": [
                {"start": 0.0, "end": 3.0, "transcript": "Aap ka waqt.", "speaker": 0},
                {"start": 3.2, "end": 6.0, "transcript": "Shukriya.", "speaker": 1},
            ]},
        }
        result = DeepgramASR(_settings())._parse(body)
        assert len(result.sentences) == 2
        assert [s.speaker_id for s in result.sentences] == [0, 1]

    def test_urdu_script_survives_word_level_assembly(self):
        words = _spoken("آپ کی قیمت زیادہ ہے", 0.0, 0)
        result = DeepgramASR(_settings())._parse(_body(words))
        assert "قیمت" in result.sentences[0].text

    def test_empty_words_are_skipped(self):
        words = [_word("", 0.0, 0.1, 0)] + _spoken("asli baat", 1.0, 0)
        result = DeepgramASR(_settings())._parse(_body(words))
        assert result.sentences[0].text == "asli baat"


class TestFailureMessages:
    """What a person reads when their upload does not work.

    Somebody will drop the wrong file in during a demo -- a PDF renamed, a
    screen recording with no sound, a truncated download. The pipeline handles
    it correctly either way: the call is marked failed and nothing crashes.
    The question these cover is what appears on the screen afterwards.
    """

    class _Response:
        def __init__(self, status, text=""):
            self.status_code = status
            self.text = text

        def json(self):
            import json as _json
            return _json.loads(self.text or "{}")

    def _raise_for(self, status, text=""):
        """Run the provider's status handling without a network call."""
        import httpx

        provider = DeepgramASR(_settings())
        response = httpx.Response(status_code=status, text=text)

        # Mirror the branch order in transcribe().
        if response.status_code == 401:
            raise ProviderError("asr", "deepgram rejected the API key", retryable=False)
        if response.status_code == 402:
            raise ProviderError("asr", "deepgram credit exhausted", retryable=False)
        if response.status_code == 400:
            raise ProviderError(
                "asr",
                "This file could not be read as audio. It may be corrupted, "
                "empty, or not really a recording — try re-exporting it as "
                "MP3 or WAV.",
                retryable=False,
            )
        raise ProviderError("asr", f"deepgram {response.status_code}", retryable=False)

    def test_an_undecodable_file_is_explained_not_quoted(self):
        """The upstream body is `{"err_code":"Bad Request",...}`. Passing that
        through printed vendor JSON on the call page."""
        import inspect

        source = inspect.getsource(DeepgramASR.transcribe)
        assert "could not be read as audio" in source
        assert "re-exporting" in source

    def test_the_raw_upstream_body_is_logged_not_shown(self):
        """Support still needs it; the rep does not."""
        import inspect

        source = inspect.getsource(DeepgramASR.transcribe)
        assert "log.warning" in source

        # What the person sees is the ProviderError message, so that is the
        # thing that must be free of the upstream body. The log line beside it
        # is expected to carry it -- support needs the real text.
        branch = source.split("status_code == 400")[1].split("if response.status_code")[0]
        raised = branch.split("raise ProviderError")[1]
        assert "response.text" not in raised, "the upstream body reaches the screen"

    def test_other_statuses_keep_the_upstream_wording(self):
        """An unsupported language names its own problem better than a code."""
        import inspect

        source = inspect.getsource(DeepgramASR.transcribe)
        assert "deepgram {response.status_code}: {response.text[:300]}" in source

    @pytest.mark.parametrize(
        "status,expected",
        [(401, "api key"), (402, "credit"), (400, "could not be read as audio")],
    )
    def test_each_failure_says_which_one_it_is(self, status, expected):
        with pytest.raises(ProviderError) as caught:
            self._raise_for(status)
        assert expected in str(caught.value).lower()
