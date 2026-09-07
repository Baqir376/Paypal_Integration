# -*- coding: utf-8 -*-
"""Speaker-diarized file transcription via Deepgram.

This exists because diarization is the one capability nothing else here could
supply. Reasoning and embeddings speak the OpenAI protocol and can point at
Gemini, Groq or Cerebras; separating two voices on a recording has no standard
protocol at all, and Model Studio -- the only provider that offered it --
requires a payment card to sign up for even its free quota. So an upload was
stored, never listened to, and analysed as a stand-in conversation.

Deepgram closes that hole: $200 of credit without a card, and Nova-3 added Urdu
with diarization, which is the combination this product actually needs.

Two things about the shape of it are worth knowing.

**The audio is posted, not fetched.** Model Studio downloads the recording
itself, which is why local storage needs a public URL, signed and expiring, and
why OSS exists in the deployment guide. Deepgram accepts the bytes in the
request body. A laptop with no public address can therefore transcribe real
calls, and none of that machinery is needed.

**Utterances, not words.** `utterances=true` returns segments already grouped
by speaker with start and end times, which is exactly the shape the metrics
engine measures. Assembling the same thing from the word stream would mean
re-implementing turn segmentation, badly.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Sequence

import httpx

from ..config import Settings
from .base import ASRResult, ASRSentence, ProviderError

log = logging.getLogger("salix.asr")

ENDPOINT = "https://api.deepgram.com/v1/listen"

#: A long call is a long upload, and Deepgram transcribes before it answers.
TIMEOUT_S = 900.0

#: Fallback when the extension says nothing. Deepgram sniffs the container
#: itself, so this only has to be plausible.
DEFAULT_MIME = "audio/mpeg"


def _mime_for(path: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    if guessed and guessed.startswith(("audio/", "video/")):
        return guessed
    return DEFAULT_MIME


class DeepgramASR:
    name = "deepgram"

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self.settings.deepgram_api_key}"}

    def _params(self, language_hints: Sequence[str], diarize: bool) -> dict[str, str]:
        """Query string for one request.

        With no hint the configured language wins, and it defaults to `multi`:
        a Pakistani sales call moves between Urdu and English inside a single
        sentence, and pinning it to either transcribes the other half as noise.

        Measured, not assumed. Asking for `en` on an Urdu recording returned a
        single unbroken segment of invented English -- and because the speakers
        could not be told apart either, the talk ratio came back as 1.0 and the
        analysis confidently described a monologue that never happened.
        """
        hints = [h.split("-")[0].lower() for h in language_hints if h]
        unique = sorted(set(hints))
        language = unique[0] if len(unique) == 1 else self.settings.deepgram_language

        params = {
            "model": self.settings.deepgram_model,
            "language": language,
            "punctuate": "true",
            # Sentence boundaries and readable numbers. The metrics engine
            # splits on punctuation, so this is load-bearing rather than
            # cosmetic: without it every turn is one unbroken sentence.
            "smart_format": "true",
            "utterances": "true",
        }
        if diarize:
            params["diarize"] = "true"
        return params

    async def _body(self, audio_url: str) -> tuple[bytes | None, dict | None, str]:
        """Resolve the audio into something to send.

        Returns `(raw_bytes, json_body, content_type)` -- exactly one of the
        first two. A remote URL is handed over as a reference so Deepgram
        fetches it; anything local is read and posted, which is the whole
        reason this provider needs no public address.
        """
        if audio_url.startswith(("http://", "https://")):
            return None, {"url": audio_url}, "application/json"

        if audio_url.startswith("data:"):
            # The Dojo's dictation fallback hands over an inline recording.
            header, _, payload = audio_url.partition(",")
            mime = header[5:].split(";")[0] or DEFAULT_MIME
            try:
                return base64.b64decode(payload), None, mime
            except Exception as exc:  # noqa: BLE001
                raise ProviderError("asr", f"unreadable inline audio: {exc}", retryable=False)

        path = Path(audio_url)
        if not path.exists():
            raise ProviderError(
                "asr",
                f"no audio at {audio_url}. Deepgram is sent the file itself, so "
                "the path has to exist on this machine.",
                retryable=False,
            )
        return path.read_bytes(), None, _mime_for(audio_url)

    async def transcribe(
        self,
        audio_url: str,
        *,
        diarize: bool = True,
        language_hints: Sequence[str] = (),
    ) -> ASRResult:
        if not self.settings.deepgram_api_key:
            raise ProviderError("asr", "no Deepgram API key configured", retryable=False)

        content, payload, content_type = await self._body(audio_url)
        headers = {**self._headers, "Content-Type": content_type}

        # Exactly one of the two, never both: httpx would otherwise have to
        # decide which wins, and the answer is version-dependent.
        sending = {"content": content} if content is not None else {"json": payload}

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                response = await client.post(
                    ENDPOINT,
                    params=self._params(language_hints, diarize),
                    headers=headers,
                    **sending,
                )
        except httpx.HTTPError as exc:
            raise ProviderError("asr", f"deepgram unreachable: {exc}", retryable=True)

        if response.status_code == 401:
            raise ProviderError("asr", "deepgram rejected the API key", retryable=False)
        if response.status_code == 402:
            raise ProviderError(
                "asr", "deepgram credit exhausted", retryable=False
            )
        if response.status_code == 400:
            # Almost always a file that is not decodable audio: a PDF renamed
            # to .mp3, a truncated download, a screen recording with no sound.
            # The upstream body for this is `{"err_code":"Bad Request",...}`,
            # and passing that through put raw vendor JSON on the call page in
            # front of whoever uploaded the wrong thing. They need to know what
            # to do, not what Deepgram calls it.
            log.warning("deepgram rejected the audio: %s", response.text[:300])
            raise ProviderError(
                "asr",
                "This file could not be read as audio. It may be corrupted, "
                "empty, or not really a recording — try re-exporting it as "
                "MP3 or WAV.",
                retryable=False,
            )

        if response.status_code >= 400:
            # Anything else keeps the upstream wording: an unsupported language
            # for the chosen model names its own problem better than a status
            # code does.
            raise ProviderError(
                "asr",
                f"deepgram {response.status_code}: {response.text[:300]}",
                retryable=response.status_code >= 500,
            )

        return self._parse(response.json())

    @staticmethod
    def _words(results: dict) -> list[dict]:
        """Every word, with its speaker and timing.

        Present whenever `diarize=true`, and the ground truth for who spoke:
        Deepgram labels each word individually, and its `utterances` are a
        convenience grouping laid on top.
        """
        channels = results.get("channels") or []
        if not channels:
            return []
        alternatives = channels[0].get("alternatives") or []
        if not alternatives:
            return []
        return alternatives[0].get("words") or []

    def _from_words(self, words: list[dict]) -> list[ASRSentence]:
        """Segment on who is speaking, rather than on when they paused.

        This exists because the utterance grouping fails on exactly the
        recordings that matter most. Two people on one speakerphone, talking
        without gaps -- which is what a real call sounds like -- came back as
        thirteen utterances for two minutes, one of them a hundred and
        twenty-two words holding eight turns from *both* people. Every number
        downstream was then computed over a transcript where the buyer's
        objections were attributed to the rep.

        The diarization was never wrong. Deepgram had labelled every one of
        those words correctly; the grouping threw the labels away by splitting
        on silence, and there was no silence to split on.

        So a new segment starts whenever the speaker changes. Within one
        speaker's run it also breaks at a real pause or at a sentence end, so
        a two-minute answer does not arrive as a single wall.
        """
        #: A pause inside one person's turn worth breaking a segment at.
        GAP_MS = 700
        #: Past this, break at the next sentence end rather than run on.
        LONG_MS = 20_000

        segments: list[ASRSentence] = []
        current: list[str] = []
        speaker = None
        begin = end = 0

        def flush():
            if current:
                segments.append(
                    ASRSentence(
                        begin_time=begin,
                        end_time=end,
                        text=" ".join(current).strip(),
                        speaker_id=int(speaker or 0),
                    )
                )

        for word in words:
            text = (word.get("punctuated_word") or word.get("word") or "").strip()
            if not text:
                continue

            # Deepgram counts in seconds; everything here is in milliseconds,
            # and every floor-control metric is computed from these numbers.
            starts = int(round(float(word.get("start", 0.0)) * 1000))
            ends = int(round(float(word.get("end", 0.0)) * 1000))
            who = int(word.get("speaker", 0) or 0)

            changed = speaker is not None and who != speaker
            paused = current and starts - end >= GAP_MS
            overran = current and end - begin >= LONG_MS and current[-1].endswith((".", "?", "!"))

            if changed or paused or overran:
                flush()
                current, begin = [], starts

            if not current:
                begin = starts
            current.append(text)
            speaker, end = who, ends

        flush()
        return segments

    def _parse(self, body: dict) -> ASRResult:
        results = body.get("results") or {}

        # Word-level first. Utterances are the fallback for a response that
        # carries no word list -- diarization turned off, or a model that does
        # not emit one -- where grouping by pause is the only option there is.
        sentences = self._from_words(self._words(results))

        if not sentences:
            for utterance in results.get("utterances") or []:
                text = (utterance.get("transcript") or "").strip()
                if not text:
                    continue
                sentences.append(
                    ASRSentence(
                        begin_time=int(round(float(utterance.get("start", 0.0)) * 1000)),
                        end_time=int(round(float(utterance.get("end", 0.0)) * 1000)),
                        text=text,
                        speaker_id=int(utterance.get("speaker", 0) or 0),
                    )
                )

        if not sentences:
            # A response with no utterances means silence, an unsupported
            # language, or a container Deepgram could not open. Saying so beats
            # returning an empty transcript that the pipeline then measures.
            raise ProviderError(
                "asr",
                "deepgram returned no speech. Check the recording has audio and "
                "that the language is supported by this model.",
                retryable=False,
            )

        metadata = body.get("metadata") or {}
        speakers = {s.speaker_id for s in sentences}
        log.info(
            "deepgram: %d utterance(s), %d speaker(s), %.1fs",
            len(sentences), len(speakers), float(metadata.get("duration", 0.0)),
        )
        if len(speakers) == 1 and len(sentences) > 4:
            # Not fatal, but every talk-ratio number downstream will be wrong,
            # and the usual cause is a stereo file with both people on one
            # channel or a recording where one side was never captured.
            log.warning(
                "deepgram found only one speaker across %d utterances; talk "
                "ratio and interruption metrics will be meaningless",
                len(sentences),
            )

        return ASRResult(
            sentences=sentences,
            language=(results.get("channels") or [{}])[0].get("detected_language")
            or self.settings.deepgram_language,
            duration_ms=int(round(float(metadata.get("duration", 0.0)) * 1000)),
            model=metadata.get("model_info", {}).get("name")
            or self.settings.deepgram_model,
        )
