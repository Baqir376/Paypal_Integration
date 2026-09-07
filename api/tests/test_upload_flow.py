"""Upload path tests.

The ingest screen is a live demo beat, so the two things that must never
regress are: a keyless upload still runs the whole DAG, and live mode fails
with an actionable message rather than a confusing upstream 400.
"""

from __future__ import annotations

import pytest

from salix.config import Settings
from salix.providers.base import ProviderError
from salix.providers.dashscope_asr import DashScopeASR
from salix.providers.mock import STAND_IN_CALL, MockASR, _classify_objection
from salix.providers.storage import LocalStorage, build_storage


class TestStandIn:
    async def test_upload_without_a_script_still_transcribes(self, tmp_path):
        """A judge clicking upload with no API key must not hit a red stage."""
        audio = tmp_path / "call_abc.mp3"
        audio.write_bytes(b"\x00" * 128)

        result = await MockASR().transcribe(str(audio))

        assert len(result.sentences) > 6
        assert {s.speaker_id for s in result.sentences} == {0, 1}

    async def test_a_script_beside_the_audio_wins(self, tmp_path):
        audio = tmp_path / "call_abc.mp3"
        audio.write_bytes(b"\x00" * 128)
        (tmp_path / "call_abc.txt").write_text(
            "REP: A specific seeded line.\nBUYER: A specific seeded reply.\n",
            encoding="utf-8",
        )

        result = await MockASR().transcribe(str(audio))

        assert len(result.sentences) == 2
        assert "specific seeded line" in result.sentences[0].text

    def test_stand_in_declares_itself(self):
        """It must be impossible to mistake for a real transcription.

        The wording no longer names Qwen. A deployment can now have live
        reasoning through some other provider while transcription stays on the
        twin, and telling that user they have "no Qwen API key" sends them to
        check a key that was never the problem.
        """
        text = STAND_IN_CALL.lower()
        assert "stand-in" in text
        assert "did not happen" in text
        assert "stored but never listened to" in text

    def test_the_stand_in_names_the_missing_capability_not_a_vendor(self):
        text = STAND_IN_CALL.lower()
        assert "speaker separation" in text or "diarization" in text
        assert "qwen api key" not in text

    def test_stand_in_exercises_both_speakers(self):
        result = MockASR.from_script(STAND_IN_CALL)
        roles = [s.speaker_id for s in result.sentences]
        assert 0 in roles and 1 in roles


class TestLiveUrlRequirement:
    async def test_a_local_path_is_rejected_with_guidance(self):
        """Model Studio fetches the audio itself, so a path cannot work. The
        error has to say what to configure instead."""
        asr = DashScopeASR(Settings(dashscope_api_key="sk-test"))

        with pytest.raises(ProviderError) as caught:
            await asr.transcribe("D:/storage/audio/call_x.mp3")

        message = str(caught.value)
        assert "publicly reachable" in message
        assert "OSS" in message or "PUBLIC_BASE_URL" in message

    @pytest.mark.parametrize(
        "url",
        ["https://example.com/a.mp3", "http://example.com/a.mp3", "data:audio/mp3;base64,AA"],
    )
    async def test_reachable_forms_pass_the_guard(self, url, monkeypatch):
        """The guard must not reject inputs the service can actually fetch, so
        it is checked up to the point of the network call."""
        asr = DashScopeASR(Settings(dashscope_api_key="sk-test"))

        async def boom(*args, **kwargs):
            raise AssertionError("reached the network, so the guard passed")

        monkeypatch.setattr(asr, "_submit", boom)

        with pytest.raises(AssertionError, match="guard passed"):
            await asr.transcribe(url)


class TestStorage:
    def test_local_storage_round_trips(self, tmp_path):
        settings = Settings(storage_dir=tmp_path)
        storage = LocalStorage(settings)

        stored, url = storage.put(b"audio-bytes", "call_x.mp3")

        assert (tmp_path / "audio" / "call_x.mp3").read_bytes() == b"audio-bytes"
        assert stored == url  # no public base configured

    def test_public_base_url_produces_a_fetchable_url(self, tmp_path):
        """Unsigned when there is no key: the deployment is open by policy at
        that point, and a signature would be proving nothing to nobody."""
        settings = Settings(
            storage_dir=tmp_path, public_base_url="https://salix.example.com/"
        )
        storage = LocalStorage(settings)

        _, url = storage.put(b"x", "call_y.mp3")

        assert url == "https://salix.example.com/audio/call_y.mp3"
        assert storage.serves_public_urls is True

    def test_with_a_key_the_url_is_signed_and_expiring(self, tmp_path):
        """This URL is handed to Model Studio, which fetches the recording from
        its own servers. The signature is the only credential it will have."""
        from urllib.parse import parse_qs, urlparse

        from salix.signing import verify

        settings = Settings(
            storage_dir=tmp_path,
            public_base_url="https://salix.example.com",
            api_key="s3cret",
        )

        _, url = LocalStorage(settings).put(b"x", "call_y.mp3")

        parsed = urlparse(url)
        assert parsed.path == "/audio/call_y.mp3"
        query = parse_qs(parsed.query)
        assert verify("s3cret", "call_y.mp3", query["expires"][0], query["sig"][0])

    def test_two_recordings_get_different_signatures(self, tmp_path):
        """So a URL for one call is not a URL for the archive."""
        settings = Settings(
            storage_dir=tmp_path,
            public_base_url="https://salix.example.com",
            api_key="s3cret",
        )
        storage = LocalStorage(settings)

        _, first = storage.put(b"x", "call_a.mp3")
        _, second = storage.put(b"x", "call_b.mp3")

        assert first.split("sig=")[1] != second.split("sig=")[1]

    def test_no_public_base_means_no_url_to_sign(self, tmp_path):
        """Local development hands back a path, and a path carries no query."""
        settings = Settings(storage_dir=tmp_path, api_key="s3cret")

        stored, url = LocalStorage(settings).put(b"x", "call_y.mp3")

        assert stored == url
        assert "sig=" not in url

    def test_defaults_to_local_without_oss_credentials(self, tmp_path):
        assert build_storage(Settings(storage_dir=tmp_path)).name == "local"


class TestObjectionClassifier:
    """The offline classifier feeds the Dojo persona, so a false positive puts
    words in a buyer's mouth that the rep never actually failed to handle."""

    @pytest.mark.parametrize(
        "line,expected",
        [
            ("That is well beyond what we were expecting to spend.", "price"),
            ("We already use Sentinel and it mostly works.", "competition"),
            ("My boss controls the budget.", "authority"),
        ],
    )
    def test_detects_real_objections(self, line, expected):
        assert _classify_objection(line) == expected

    @pytest.mark.parametrize(
        "line",
        [
            "That is sensible, and it also solves a problem for me, because of the cost.",
            "That is fair, and the pricing makes sense when you put it that way.",
            "No argument there, four hours is better than days.",
        ],
    )
    def test_agreement_is_not_an_objection(self, line):
        assert _classify_objection(line) is None

    def test_neutral_line_is_not_an_objection(self):
        assert _classify_objection("We have about four hundred contracts.") is None
