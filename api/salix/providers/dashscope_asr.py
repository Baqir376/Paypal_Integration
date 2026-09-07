"""Speaker-diarized file transcription via Model Studio.

Implemented against the native DashScope REST surface rather than the SDK,
because the async task flow needs real control over polling, timeouts and
partial failure -- and because httpx keeps the whole pipeline on one async
event loop.

The flow, per Alibaba Cloud docs:

    POST {base}/services/audio/asr/transcription   header X-DashScope-Async
      -> { output: { task_id } }
    GET  {base}/tasks/{task_id}
      -> { output: { task_status, results: [{ transcription_url }] } }
    GET  transcription_url
      -> { transcripts: [{ sentences: [{begin_time,end_time,text,speaker_id}] }] }

Only `qwen-audio-3.0-asr-flash-filetrans`, `fun-asr` and the Paraformer v2
family support `diarization_enabled`, and diarized audio must be mono.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Sequence

import httpx

from ..config import Settings
from .base import ASRResult, ASRSentence, ProviderError

log = logging.getLogger("salix.asr")

TERMINAL_OK = {"SUCCEEDED"}
TERMINAL_BAD = {"FAILED", "CANCELED", "UNKNOWN"}


class DashScopeASR:
    name = "dashscope"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._headers = {
            "Authorization": f"Bearer {settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }

    async def transcribe(
        self,
        audio_url: str,
        *,
        diarize: bool = True,
        language_hints: Sequence[str] = (),
    ) -> ASRResult:
        if not self.settings.dashscope_api_key:
            raise ProviderError("asr", "no API key configured", retryable=False)

        # Model Studio fetches the audio itself, so it must be given a URL it
        # can reach. Failing here with an actionable message beats a confusing
        # 400 from the upstream service.
        if not audio_url.lower().startswith(("http://", "https://", "data:")):
            raise ProviderError(
                "asr",
                "Live transcription needs a publicly reachable audio URL, but "
                f"was given a local path ({audio_url}). Configure OSS "
                "(SALIX_OSS_BUCKET and credentials) or set "
                "SALIX_PUBLIC_BASE_URL so uploads are fetchable.",
                retryable=False,
            )

        async with httpx.AsyncClient(timeout=60.0) as client:
            task_id = await self._submit(client, audio_url, diarize, language_hints)
            transcription_url = await self._poll(client, task_id)
            payload = await self._fetch(client, transcription_url)

        return self._parse(payload)

    # -- steps -----------------------------------------------------------

    async def _submit(
        self,
        client: httpx.AsyncClient,
        audio_url: str,
        diarize: bool,
        language_hints: Sequence[str],
    ) -> str:
        body: dict[str, Any] = {
            "model": self.settings.model_asr_file,
            "input": {"file_urls": [audio_url]},
            "parameters": {
                "channel_id": [0],
                "diarization_enabled": diarize,
                # This API requires a list, so an unknown language becomes the
                # widest guess it accepts rather than an empty field.
                "language_hints": list(language_hints) or ["en", "ur"],
            },
        }
        url = f"{self.settings.dashscope_base_url}/services/audio/asr/transcription"
        headers = {**self._headers, "X-DashScope-Async": "enable"}

        response = await client.post(url, headers=headers, json=body)
        if response.status_code >= 400:
            raise ProviderError(
                "asr", f"submit failed {response.status_code}: {response.text[:400]}"
            )

        data = response.json()
        task_id = (data.get("output") or {}).get("task_id")
        if not task_id:
            raise ProviderError("asr", f"no task_id in response: {data}")
        log.info("asr task submitted: %s", task_id)
        return task_id

    async def _poll(self, client: httpx.AsyncClient, task_id: str) -> str:
        url = f"{self.settings.dashscope_base_url}/tasks/{task_id}"
        deadline = time.monotonic() + self.settings.asr_max_wait_s
        interval = self.settings.asr_poll_interval_s

        while time.monotonic() < deadline:
            response = await client.get(url, headers=self._headers)
            if response.status_code >= 400:
                raise ProviderError(
                    "asr", f"poll failed {response.status_code}: {response.text[:300]}"
                )

            output = response.json().get("output") or {}
            status = (output.get("task_status") or "").upper()

            if status in TERMINAL_OK:
                results = output.get("results") or []
                for result in results:
                    if (result.get("subtask_status") or "").upper() == "SUCCEEDED":
                        link = result.get("transcription_url")
                        if link:
                            return link
                raise ProviderError("asr", f"no successful subtask: {results}")

            if status in TERMINAL_BAD:
                reason = output.get("message") or output.get("code") or status
                raise ProviderError("asr", f"task {status}: {reason}")

            await asyncio.sleep(interval)
            # Back off gently on long files rather than hammering the endpoint.
            interval = min(interval * 1.25, 10.0)

        raise ProviderError(
            "asr", f"timed out after {self.settings.asr_max_wait_s}s", retryable=True
        )

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> dict[str, Any]:
        response = await client.get(url)
        if response.status_code >= 400:
            raise ProviderError("asr", f"result fetch failed {response.status_code}")
        return response.json()

    # -- parsing ---------------------------------------------------------

    def _parse(self, payload: dict[str, Any]) -> ASRResult:
        sentences: list[ASRSentence] = []

        for transcript in payload.get("transcripts") or []:
            for raw in transcript.get("sentences") or []:
                text = (raw.get("text") or "").strip()
                if not text:
                    continue
                begin = int(raw.get("begin_time") or 0)
                end = int(raw.get("end_time") or begin)
                if end <= begin:
                    end = begin + max(400, len(text.split()) * 300)
                sentences.append(
                    ASRSentence(
                        begin_time=begin,
                        end_time=end,
                        text=text,
                        speaker_id=int(raw.get("speaker_id") or 0),
                        emotion=raw.get("emotion"),
                    )
                )

        if not sentences:
            raise ProviderError("asr", "transcription returned no sentences")

        sentences.sort(key=lambda s: (s.begin_time, s.end_time))
        return ASRResult(
            sentences=sentences,
            duration_ms=max(s.end_time for s in sentences),
            model=self.settings.model_asr_file,
        )
