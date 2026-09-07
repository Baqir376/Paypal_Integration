"""Provider interfaces.

Every outbound call in Salix goes through one of these Protocols. Nothing in
`agents/` or `pipeline/` imports an SDK directly, which is what makes the whole
system runnable with no API key -- and what makes a network failure degrade a
single panel instead of the page.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Optional, Protocol, Sequence, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ProviderError(RuntimeError):
    """Raised when an upstream provider fails in a way we cannot recover from.

    Callers are expected to catch this and degrade, never to let it reach the
    HTTP layer as a 500.
    """

    def __init__(self, provider: str, detail: str, *, retryable: bool = False):
        super().__init__(f"{provider}: {detail}")
        self.provider = provider
        self.detail = detail
        self.retryable = retryable


class ASRSentence(BaseModel):
    """One diarized sentence, mirroring the Model Studio result shape."""

    begin_time: int
    end_time: int
    text: str
    speaker_id: int = 0
    emotion: Optional[str] = None


class ASRResult(BaseModel):
    sentences: list[ASRSentence]
    language: str = "en"
    duration_ms: int = 0
    model: str = ""


@runtime_checkable
class ASRProvider(Protocol):
    """Offline file transcription with speaker diarization."""

    name: str

    async def transcribe(
        self,
        audio_url: str,
        *,
        diarize: bool = True,
        # Empty means "nobody knows", which is the truth for an uploaded
        # recording: no screen asks and no caller can tell. It used to default
        # to ("en",), and a provider cannot distinguish that from a caller who
        # genuinely means English -- so an Urdu call was transcribed as English
        # and came back as a page of confident nonsense.
        language_hints: Sequence[str] = (),
    ) -> ASRResult: ...


@runtime_checkable
class LLMProvider(Protocol):
    """Text generation, with a structured mode that returns a validated model."""

    name: str

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str: ...

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
    ) -> T: ...

    async def stream(
        self,
        *,
        system: str,
        user: str,
        history: Optional[list[dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.6,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dim: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@runtime_checkable
class TTSProvider(Protocol):
    name: str

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        instruction: str = "",
        out_path: Optional[str] = None,
    ) -> bytes: ...

    def voices(self) -> list[str]: ...


class Providers(BaseModel):
    """The bundle handed to agents. Assembled once at startup."""

    model_config = {"arbitrary_types_allowed": True}

    llm: Any
    asr: Any
    tts: Any
    embeddings: Any
    mode: str = "mock"
