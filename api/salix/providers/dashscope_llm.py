"""Qwen text generation via the OpenAI-compatible Model Studio endpoint.

The interesting part is `structured()`. Getting reliable typed output from a
language model needs three things, all implemented here:

1. The JSON Schema in the prompt, plus `response_format=json_object` so the
   decoder is constrained at generation time.
2. Tolerant extraction, because models still wrap JSON in prose or fences.
3. A repair loop that hands the *validation error itself* back to the model.
   In practice this converts most first-attempt failures into second-attempt
   successes, which is the difference between a demo that works and one that
   throws.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator, Optional, TypeVar

from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from ..config import Settings
from .base import ProviderError

log = logging.getLogger("salix.llm")

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(raw: str) -> str:
    """Pull a JSON object out of a model response.

    Handles the three things models actually do: return clean JSON, wrap it in
    a markdown fence, or bracket it with a sentence of commentary.
    """
    text = raw.strip()
    if not text:
        raise ValueError("empty response")

    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in response")
    return text[start : end + 1]


class DashScopeLLM:
    """Async text client, speaking plain OpenAI protocol.

    Named for its default rather than its only destination: Model Studio is a
    standard OpenAI-compatible endpoint, so the same client drives Gemini,
    Groq, Cerebras or anything else once `llm_base_url` is set. One instance is
    shared for the process lifetime.
    """

    name = "dashscope"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.name = settings.llm_provider_name
        self._client = AsyncOpenAI(
            api_key=settings.llm_key or "missing",
            base_url=settings.llm_endpoint,
            timeout=settings.llm_timeout_s,
            max_retries=0,  # retries handled here so we can log and classify
        )

    # -- internals -------------------------------------------------------

    def _capped(self, max_tokens: int) -> int:
        cap = self.settings.llm_max_tokens_cap
        return min(max_tokens, cap) if cap else max_tokens

    async def _chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        response_format: Optional[dict[str, str]] = None,
    ) -> str:
        attempts = self.settings.max_retries
        last: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": self._capped(max_tokens),
                }
                if response_format:
                    kwargs["response_format"] = response_format
                response = await self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                if not content.strip():
                    raise ValueError("model returned empty content")
                return content
            except (RateLimitError, APITimeoutError) as exc:
                last = exc
                delay = min(8.0, 1.5 * (2 ** (attempt - 1)))
                log.warning(
                    "llm transient failure (%s), attempt %d/%d, retrying in %.1fs",
                    type(exc).__name__, attempt, attempts, delay,
                )
                import asyncio

                await asyncio.sleep(delay)
            except APIError as exc:
                last = exc
                status = getattr(exc, "status_code", None)
                if status and 400 <= status < 500 and status not in (408, 429):
                    raise ProviderError(
                        self.settings.llm_provider_name,
                        f"{status}: {exc}",
                        retryable=False,
                    )
                import asyncio

                await asyncio.sleep(1.0 * attempt)
            except Exception as exc:  # noqa: BLE001 - surface as ProviderError
                last = exc
                import asyncio

                await asyncio.sleep(0.5 * attempt)

        raise ProviderError(
            self.settings.llm_provider_name, f"exhausted retries: {last}", retryable=True
        )

    # -- public API ------------------------------------------------------

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        return await self._chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model=model or self.settings.fast_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
        repair_attempts: int = 2,
    ) -> T:
        json_schema = json.dumps(schema.model_json_schema(), indent=2)
        system_with_schema = (
            f"{system}\n\n"
            "Respond with a single JSON object and nothing else. No prose, no "
            "markdown fence, no commentary. It must validate against this JSON "
            f"Schema:\n\n{json_schema}"
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_with_schema},
            {"role": "user", "content": user},
        ]

        last_error = ""
        for attempt in range(repair_attempts + 1):
            raw = await self._chat(
                messages,
                model=model or self.settings.deep_model,
                temperature=temperature if attempt == 0 else 0.0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            try:
                return schema.model_validate_json(extract_json(raw))
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)[:1500]
                log.warning(
                    "structured output failed validation for %s (attempt %d): %s",
                    schema.__name__, attempt + 1, last_error[:300],
                )
                # Hand the model its own output and the exact validator
                # complaint. This is far more effective than simply retrying.
                messages = messages[:2] + [
                    {"role": "assistant", "content": raw[:6000]},
                    {
                        "role": "user",
                        "content": (
                            "That response failed schema validation with the "
                            f"following error:\n\n{last_error}\n\n"
                            "Return the corrected JSON object only. Fix exactly "
                            "what the error describes and change nothing else."
                        ),
                    },
                ]

        raise ProviderError(
            self.settings.llm_provider_name,
            f"could not produce valid {schema.__name__} after "
            f"{repair_attempts + 1} attempts: {last_error}",
            retryable=False,
        )

    async def stream(
        self,
        *,
        system: str,
        user: str,
        history: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.6,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user})

        try:
            stream = await self._client.chat.completions.create(
                model=model or self.settings.fast_model,
                messages=messages,
                temperature=temperature,
                max_tokens=self._capped(max_tokens),
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                self.settings.llm_provider_name, f"stream failed: {exc}", retryable=True
            )


class DashScopeEmbeddings:
    """Embeddings over the OpenAI protocol, wherever they are hosted.

    Named for its origin; it is no longer DashScope-specific. `embeddings.create`
    is part of the protocol, so any compatible endpoint hosting an embedding
    model can serve this -- which is what lets somebody who cannot give Alibaba
    a payment card still have genuinely semantic retrieval instead of the
    hash-based twin.
    """

    # The endpoint caps how many strings one request may carry.
    BATCH_SIZE = 10

    def __init__(self, settings: Settings):
        self.settings = settings
        self.dim = settings.embedding_dim
        self.model = settings.embedding_model
        self.name = "dashscope" if settings.dashscope_api_key else settings.llm_provider_name
        #: Set once a request has told us this endpoint rejects `dimensions`.
        self._omit_dimensions = False
        self._client = AsyncOpenAI(
            api_key=settings.embedding_key or "missing",
            base_url=settings.embedding_endpoint,
            timeout=settings.llm_timeout_s,
            max_retries=2,
        )

    async def _create(self, batch: list[str]):
        """One request, retried once without `dimensions` if that is the problem.

        `dimensions` is optional in the protocol and not every host implements
        it. Sending it to one that does not fails the whole call, and the only
        way to know is to be told -- so we ask once, remember the answer, and
        stop asking.
        """
        if not self._omit_dimensions:
            try:
                return await self._client.embeddings.create(
                    model=self.model, input=batch, dimensions=self.dim
                )
            except Exception as exc:  # noqa: BLE001
                if "dimension" not in str(exc).lower():
                    raise
                log.info(
                    "%s does not accept `dimensions`; using the model default",
                    self.name,
                )
                self._omit_dimensions = True

        return await self._client.embeddings.create(model=self.model, input=batch)

    async def embed(self, texts):
        texts = list(texts)
        if not texts:
            return []

        out: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = [t[:8000] or " " for t in texts[i : i + self.BATCH_SIZE]]
            try:
                response = await self._create(batch)
            except Exception as exc:  # noqa: BLE001
                raise ProviderError("embeddings", str(exc), retryable=True)

            for item in response.data:
                vector = item.embedding
                # The stored index has a fixed width, and a model that returns
                # a different one would corrupt every cosine comparison against
                # rows already written. Say so here rather than let search go
                # quietly wrong.
                if len(vector) != self.dim:
                    raise ProviderError(
                        "embeddings",
                        f"{self.model} returned {len(vector)} dimensions, but the "
                        f"index is {self.dim}. Set SALIX_EMBEDDING_DIM="
                        f"{len(vector)} and re-seed.",
                        retryable=False,
                    )
                out.append(vector)
        return out
