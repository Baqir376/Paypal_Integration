"""Provider assembly.

One factory, called once at startup, decides whether Salix talks to Alibaba
Cloud or to its offline twins. Nothing downstream knows or cares which.
"""

from __future__ import annotations

import logging

from ..config import Settings, get_settings
from .base import (
    ASRProvider,
    ASRResult,
    ASRSentence,
    EmbeddingProvider,
    LLMProvider,
    ProviderError,
    Providers,
    TTSProvider,
)
from .mock import MockASR, MockEmbeddings, MockLLM, MockTTS

log = logging.getLogger("salix.providers")

_bundle: Providers | None = None


def build_providers(settings: Settings | None = None) -> Providers:
    settings = settings or get_settings()

    # The two halves are decided separately. Text speaks OpenAI protocol and
    # can point anywhere; transcription, speech and embeddings are DashScope
    # services with no standard protocol, so they need that key specifically.
    # A Gemini key alone therefore buys real analysis on offline audio -- which
    # is a perfectly coherent setup, and used to be impossible to express.
    llm_live = settings.llm_is_live
    native_live = settings.dashscope_is_live

    if llm_live or native_live or settings.asr_is_live:
        # Imported lazily so that offline mode never pays for the SDK import.
        from .dashscope_llm import DashScopeEmbeddings
        from .failover import build_llm
        from .dashscope_tts import DashScopeTTS

        def _asr():
            """Whoever can actually separate the speakers.

            Deepgram first when both are configured: it takes the audio in the
            request body, so it works from a laptop with no public address,
            where Model Studio needs a URL it can reach.
            """
            if settings.deepgram_api_key:
                from .deepgram_asr import DeepgramASR

                return DeepgramASR(settings)
            if native_live:
                from .dashscope_asr import DashScopeASR

                return DashScopeASR(settings)
            return MockASR(settings)

        log.info(
            "providers: text=%s (%s via %s), asr=%s (%s), speech=%s",
            "LIVE" if llm_live else "MOCK",
            settings.deep_model,
            settings.llm_provider_name,
            "LIVE" if settings.asr_is_live else "MOCK",
            settings.asr_provider_name,
            "LIVE" if native_live else "MOCK",
        )
        return Providers(
            llm=build_llm(settings) if llm_live else MockLLM(settings),
            asr=_asr(),
            tts=DashScopeTTS(settings) if native_live else MockTTS(settings),
            embeddings=(
                DashScopeEmbeddings(settings)
                if settings.embeddings_is_live
                else MockEmbeddings(settings)
            ),
            mode="live",
        )

    log.info("providers: MOCK (no model key found; running on the offline twins)")
    return Providers(
        llm=MockLLM(settings),
        asr=MockASR(settings),
        tts=MockTTS(settings),
        embeddings=MockEmbeddings(settings),
        mode="mock",
    )


def get_providers() -> Providers:
    global _bundle
    if _bundle is None:
        _bundle = build_providers()
    return _bundle


def reset_providers() -> None:
    """Drop the cached bundle. Used by tests and by the runtime mode switch."""
    global _bundle
    _bundle = None


__all__ = [
    "ASRProvider",
    "ASRResult",
    "ASRSentence",
    "EmbeddingProvider",
    "LLMProvider",
    "MockASR",
    "MockEmbeddings",
    "MockLLM",
    "MockTTS",
    "ProviderError",
    "Providers",
    "TTSProvider",
    "build_providers",
    "get_providers",
    "reset_providers",
]
