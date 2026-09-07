"""Runtime configuration.

Salix runs in three modes, chosen by `SALIX_PROVIDER_MODE`:

* `live`  -- every call goes to Alibaba Cloud Model Studio.
* `mock`  -- deterministic local fakes, no network, no API key.
* `auto`  -- live if an API key is present, mock otherwise. This is the default
             so a fresh clone runs end to end with zero setup.

The three-mode arrangement is what lets the seeded demo be immune to venue
wifi while still being one environment variable away from real inference.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = API_DIR.parent


class ProviderMode(str, Enum):
    LIVE = "live"
    MOCK = "mock"
    AUTO = "auto"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SALIX_",
        env_file=(REPO_DIR / ".env", API_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Credentials ----------------------------------------------------
    # Read from DASHSCOPE_API_KEY too, since that is the name every Alibaba
    # Cloud snippet uses and nobody should have to rename it.
    dashscope_api_key: Optional[str] = None
    dashscope_workspace_id: Optional[str] = None
    dashscope_region: str = "ap-southeast-1"

    # --- Bring your own text model ----------------------------------------
    # Any OpenAI-compatible endpoint. Set these and the reasoning and play
    # extraction run there instead of on Model Studio; leave them unset and
    # nothing changes. Transcription, speech and embeddings are unaffected --
    # they are not OpenAI-protocol services and stay on DashScope or on the
    # offline twins.
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model_deep: Optional[str] = None
    llm_model_fast: Optional[str] = None

    provider_mode: ProviderMode = ProviderMode.AUTO

    # --- Models ---------------------------------------------------------
    # Verified against Alibaba Cloud Model Studio docs. Only the file
    # transcription model below supports speaker diarization.
    model_deep: str = "qwen3.8-max"
    model_fast: str = "qwen-plus"
    model_asr_file: str = "qwen-audio-3.0-asr-flash-filetrans"
    model_asr_realtime: str = "fun-asr-realtime"
    model_tts: str = "qwen3-tts-instruct-flash"
    model_embedding: str = "text-embedding-v4"
    embedding_dim: int = 1024

    #: An embedding model on the bring-your-own endpoint, if it has one.
    #:
    #: Retrieval is not a nice-to-have here: it is what makes the playbook cite
    #: a colleague's actual call instead of an arbitrary one. The offline twin
    #: hashes text into a stable vector, which exercises the whole storage and
    #: cosine path honestly but is not semantic, so citations come back
    #: unrelated to the question.
    #:
    #: Alibaba's card requirement puts real embeddings out of reach for anyone
    #: who cannot give one, and Gemini's free tier has an embedding model on
    #: the same OpenAI-compatible surface. Naming it here is enough.
    llm_model_embedding: Optional[str] = None

    # --- Transcription with speaker separation -----------------------------
    # The one capability with no standard protocol, and the reason an upload
    # used to be stored and never listened to. Model Studio can do it and
    # wants a payment card; Deepgram gives $200 of credit without one, and
    # Nova-3 covers Urdu.
    deepgram_api_key: Optional[str] = None
    deepgram_model: str = "nova-3"
    #: `multi` rather than `en`, because a Pakistani sales call moves between
    #: Urdu and English inside one sentence and pinning it to either
    #: transcribes the other half as noise.
    deepgram_language: str = "multi"

    #: `roman` or `native`.
    #:
    #: The product writes both its languages in Latin letters, and speech
    #: recognition does not: Urdu comes back as Nastaliq, or as Devanagari,
    #: which is Hindi's script and which `detect_language` reads as English.
    #: `roman` transliterates a transcript before anything measures it, so one
    #: script reaches the screen and the metrics engine both.
    #:
    #: Set `native` to keep whatever the transcriber produced -- correct if the
    #: floor reads Urdu script and wants it preserved.
    transcript_script: str = "roman"

    # --- Infrastructure -------------------------------------------------
    database_url: str = f"sqlite+aiosqlite:///{(REPO_DIR / 'salix.db').as_posix()}"

    # Object storage. Model Studio fetches audio itself, so a deployed Salix
    # needs somewhere the service can reach. Leave blank for local disk.
    oss_endpoint: str = "oss-ap-southeast-1.aliyuncs.com"
    oss_bucket: Optional[str] = None
    oss_access_key_id: Optional[str] = None
    oss_access_key_secret: Optional[str] = None
    oss_prefix: str = "salix/audio"

    # Where this API is reachable from the internet. Lets local disk serve
    # transcribable URLs through a tunnel or a deployed host.
    public_base_url: Optional[str] = None

    storage_dir: Path = REPO_DIR / "storage"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Serving in front of real people ----------------------------------
    # A shared key on /api. Unset means open, which is right for a laptop and
    # wrong for anything reachable from outside it -- the process says so at
    # startup rather than leaving it to be discovered.
    api_key: Optional[str] = None

    #: Courtesy limits on the endpoints that cost tokens, money or minutes.
    rate_limit_enabled: bool = True

    #: Refuse an upload larger than this before reading it into memory.
    max_upload_mb: int = 200

    # --- Behaviour ------------------------------------------------------
    llm_timeout_s: float = 120.0
    asr_poll_interval_s: float = 3.0
    asr_max_wait_s: float = 900.0
    max_retries: int = 3

    @property
    def resolved_mode(self) -> ProviderMode:
        if self.provider_mode is not ProviderMode.AUTO:
            return self.provider_mode
        if self.dashscope_api_key or self.llm_api_key:
            return ProviderMode.LIVE
        return ProviderMode.MOCK

    @property
    def is_live(self) -> bool:
        return self.resolved_mode is ProviderMode.LIVE

    # --- What the text layer actually talks to -----------------------------

    @property
    def llm_key(self) -> Optional[str]:
        """The key the reasoning layer uses. An override wins over DashScope."""
        return self.llm_api_key or self.dashscope_api_key

    @property
    def llm_endpoint(self) -> str:
        """The OpenAI-compatible base URL the reasoning layer talks to."""
        return self.llm_base_url or self.compatible_base_url

    @property
    def deep_model(self) -> str:
        return self.llm_model_deep or self.model_deep

    @property
    def fast_model(self) -> str:
        return self.llm_model_fast or self.model_fast

    @property
    def llm_provider_name(self) -> str:
        """A short, honest name for whoever is answering the text calls.

        Derived from the host rather than declared, so it cannot drift out of
        step with where the requests are actually going.
        """
        host = (self.llm_endpoint or "").lower()
        for fragment, name in (
            ("dashscope", "alibaba model studio"),
            ("aliyuncs", "alibaba model studio"),
            ("generativelanguage.googleapis", "google gemini"),
            ("groq", "groq"),
            ("cerebras", "cerebras"),
            ("openrouter", "openrouter"),
            ("mistral", "mistral"),
            ("api.openai.com", "openai"),
            ("localhost", "local"),
            ("127.0.0.1", "local"),
        ):
            if fragment in host:
                return name
        return "openai-compatible"

    @property
    def llm_is_live(self) -> bool:
        if self.provider_mode is not ProviderMode.AUTO:
            return self.is_live
        return bool(self.llm_key)

    @property
    def asr_is_live(self) -> bool:
        """Can a real recording actually be transcribed and diarized?

        Its own question, separate from every other capability. A deployment
        can reason through Gemini, embed through Gemini and transcribe through
        Deepgram, and reporting any of those three as a single "live" would be
        wrong about the other two.
        """
        if self.provider_mode is not ProviderMode.AUTO:
            return self.is_live
        return bool(self.deepgram_api_key or self.dashscope_api_key)

    @property
    def asr_provider_name(self) -> str:
        """Who is listening. Deepgram wins when both are configured: it takes
        the audio in the request body, so it works without the public URL,
        signed or otherwise, that Model Studio requires."""
        if self.deepgram_api_key:
            return "deepgram"
        if self.dashscope_api_key:
            return "alibaba model studio"
        return "offline twin"

    @property
    def asr_model(self) -> str:
        if self.deepgram_api_key:
            return self.deepgram_model
        return self.model_asr_file

    @property
    def dashscope_is_live(self) -> bool:
        """Transcription and speech need DashScope specifically.

        Diarized file transcription and Qwen TTS have no standard protocol, so
        nothing else can stand in for them.
        """
        if self.provider_mode is not ProviderMode.AUTO:
            return self.is_live
        return bool(self.dashscope_api_key)

    @property
    def embeddings_is_live(self) -> bool:
        """Embeddings are the one audio-adjacent capability that is portable.

        `embeddings.create` is part of the OpenAI protocol, so any compatible
        endpoint that hosts an embedding model can serve them -- which is what
        lets somebody without a payment card have genuinely semantic search.
        """
        if self.provider_mode is not ProviderMode.AUTO:
            return self.is_live
        if self.dashscope_api_key:
            return True
        return bool(self.llm_key and self.llm_model_embedding)

    @property
    def embedding_model(self) -> str:
        """The embedding model actually being called."""
        if not self.dashscope_api_key and self.llm_model_embedding:
            return self.llm_model_embedding
        return self.model_embedding

    @property
    def embedding_endpoint(self) -> str:
        """Where the embedding calls go, which need not be where the text goes."""
        if not self.dashscope_api_key and self.llm_model_embedding and self.llm_base_url:
            return self.llm_base_url
        return self.compatible_base_url

    @property
    def embedding_key(self) -> str:
        if not self.dashscope_api_key and self.llm_model_embedding:
            return self.llm_key or ""
        return self.dashscope_api_key or ""

    @property
    def compatible_base_url(self) -> str:
        """OpenAI-compatible endpoint for all text and embedding calls.

        Workspace-scoped hosts are preferred when a workspace id is configured;
        otherwise we fall back to the shared international endpoint, which
        works with a plain API key.
        """
        if self.dashscope_workspace_id:
            return (
                f"https://{self.dashscope_workspace_id}"
                f".{self.dashscope_region}.maas.aliyuncs.com/compatible-mode/v1"
            )
        return "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    @property
    def dashscope_base_url(self) -> str:
        """Native DashScope endpoint, used for async file transcription."""
        if self.dashscope_workspace_id:
            return (
                f"https://{self.dashscope_workspace_id}"
                f".{self.dashscope_region}.maas.aliyuncs.com/api/v1"
            )
        return "https://dashscope-intl.aliyuncs.com/api/v1"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def audio_dir(self) -> Path:
        return self.storage_dir / "audio"


@lru_cache
def get_settings() -> Settings:
    import os

    settings = Settings()

    # A blank environment variable means "not set", not "set to empty".
    #
    # Every orchestrator writes optional values through as empty strings --
    # `SALIX_DATABASE_URL: ${SALIX_DATABASE_URL:-}` in a compose file is the
    # normal way to make a setting optional, and it arrives as "". Taken
    # literally that overrode the SQLite default with an unparseable URL and
    # the container died at startup with a SQLAlchemy stack trace, which is a
    # miserable thing to debug from a deployment log.
    #
    # Only fields with a meaningful non-empty default are listed: leaving a
    # key blank must still mean no key.
    for field in ("database_url", "storage_dir", "cors_origins", "dashscope_region"):
        if isinstance(getattr(settings, field, None), str) and not getattr(settings, field).strip():
            setattr(settings, field, type(settings).model_fields[field].default)

    # Accept the conventional unprefixed name as a fallback.
    if not settings.dashscope_api_key:
        settings.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
    if not settings.dashscope_workspace_id:
        settings.dashscope_workspace_id = os.getenv("DASHSCOPE_WORKSPACE_ID")
    # Unprefixed names too, because that is what every provider's own snippet
    # tells you to export.
    if not settings.llm_api_key:
        settings.llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not settings.llm_base_url:
        settings.llm_base_url = os.getenv("LLM_BASE_URL")
    if not settings.api_key:
        settings.api_key = os.getenv("SALIX_API_KEY")
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    return settings
