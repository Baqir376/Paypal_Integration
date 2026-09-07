"""Qwen TTS, used to synthesize the seed call corpus and the Dojo buyer voice.

Model Studio exposes TTS two ways: a WebSocket realtime protocol, and
non-realtime synthesis through the multimodal-generation endpoint. We use the
latter, because both callers here want a complete audio file rather than a
stream, and a single request is far easier to make robust.

Response parsing is deliberately tolerant: the payload has carried the audio as
a signed URL and, in other model versions, as inline base64. We accept either.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Optional

import httpx

from ..config import Settings
from .base import ProviderError

log = logging.getLogger("salix.tts")

# Distinct voices for the seed corpus, so diarization has genuinely different
# speakers to separate rather than one voice talking to itself.
VOICE_POOL: tuple[str, ...] = (
    "Cherry", "Ethan", "Nofish", "Jennifer", "Ryan", "Katerina", "Elias", "Dylan",
)


class DashScopeTTS:
    name = "dashscope"

    ENDPOINT = "/services/aigc/multimodal-generation/generation"

    def __init__(self, settings: Settings):
        self.settings = settings

    def voices(self) -> list[str]:
        return list(VOICE_POOL)

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        instruction: str = "",
        out_path: Optional[str] = None,
    ) -> bytes:
        if not self.settings.dashscope_api_key:
            raise ProviderError("tts", "no API key configured", retryable=False)

        body: dict[str, Any] = {
            "model": self.settings.model_tts,
            "input": {"text": text, "voice": voice},
            "parameters": {"language_type": "English"},
        }
        if instruction:
            # Instruction-controllable models take prosody direction in words.
            body["input"]["instruction"] = instruction

        url = self.settings.dashscope_base_url + self.ENDPOINT
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=body)
            if response.status_code >= 400:
                raise ProviderError(
                    "tts", f"{response.status_code}: {response.text[:400]}"
                )
            audio = await self._extract_audio(client, response.json())

        if out_path:
            path = Path(out_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(audio)
        return audio

    async def _extract_audio(
        self, client: httpx.AsyncClient, payload: dict[str, Any]
    ) -> bytes:
        output = payload.get("output") or {}
        audio = output.get("audio") or {}

        if isinstance(audio, dict):
            if audio.get("url"):
                fetched = await client.get(audio["url"])
                if fetched.status_code >= 400:
                    raise ProviderError("tts", "audio url fetch failed")
                return fetched.content
            if audio.get("data"):
                return base64.b64decode(audio["data"])

        # Some model versions nest the audio under choices[].message.content[].
        for choice in output.get("choices") or []:
            for part in (choice.get("message") or {}).get("content") or []:
                if isinstance(part, dict) and part.get("audio"):
                    inner = part["audio"]
                    if isinstance(inner, dict) and inner.get("data"):
                        return base64.b64decode(inner["data"])
                    if isinstance(inner, str):
                        return base64.b64decode(inner)

        raise ProviderError("tts", f"no audio in response: {str(payload)[:300]}")
