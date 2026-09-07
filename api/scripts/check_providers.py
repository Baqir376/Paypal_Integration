# -*- coding: utf-8 -*-
"""Is this key actually working?

Run after putting a key in .env, before wondering why the badge still says
offline:

    cd api
    .venv/Scripts/python -m scripts.check_providers

Configuration is not the same as working. A key can be present and mistyped, or
correct but out of quota, or correct for a region the config does not point at.
All three look identical in `.env` and produce a different failure much later,
usually in the middle of a seven-stage pipeline, wrapped in a stack trace about
something else.

So this calls each capability for real -- one tiny request each -- and says
which ones answered.

The four are reported separately on purpose, because they are not one switch.

Reasoning and embeddings both speak the OpenAI protocol and can point at
Gemini, Groq, Cerebras or anything else. Transcription and speech cannot:
diarized file transcription and Qwen TTS have no standard protocol, and
separating the two speakers is what every talk-ratio and interruption number
is computed from.

So a Gemini key alone buys real reasoning *and* real semantic search, with only
the audio path still on its twin. That is a coherent setup, it is the only one
available to somebody who cannot give Alibaba a payment card, and it is
confusing to discover by accident.

The embedding check goes further than "did it answer": it embeds two related
sentences and one unrelated one and confirms the related pair really is closer.
The offline twin answers every request in the right shape and means nothing by
it, so shape alone proves nothing.
"""

from __future__ import annotations

import asyncio
import sys

# Run from api/ as `python -m scripts.check_providers`.
sys.path.insert(0, ".")

from salix.config import get_settings  # noqa: E402
from salix.providers import build_providers  # noqa: E402

GREEN, RED, DIM, YELLOW, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[33m", "\033[0m"


def line(name: str, state: str, detail: str = "") -> None:
    colour = {"live": GREEN, "offline": DIM, "broken": RED}[state]
    label = {"live": "LIVE", "offline": "offline twin", "broken": "BROKEN"}[state]
    print(f"  {name:<16} {colour}{label:<14}{OFF} {detail}")


async def main() -> int:
    settings = get_settings()
    providers = build_providers(settings)

    print()
    print(f"  provider mode    {providers.mode.upper()}")
    print(f"  reasoning via    {settings.llm_provider_name}")
    print(f"  deep model       {settings.deep_model}")
    print()

    failures: list[str] = []

    # --- reasoning ---------------------------------------------------------
    if settings.llm_is_live:
        try:
            reply = await providers.llm.complete(
                system="Reply with the single word OK.", user="ping"
            )
            text = (reply or "").strip().replace("\n", " ")[:40]
            if text:
                line("reasoning", "live", f'answered "{text}"')
            else:
                line("reasoning", "broken", "empty response")
                failures.append("reasoning")
        except Exception as exc:  # noqa: BLE001
            line("reasoning", "broken", f"{type(exc).__name__}: {exc}"[:110])
            failures.append("reasoning")
    else:
        line("reasoning", "offline", "no text-model key configured")

    # --- embeddings --------------------------------------------------------
    # Retrieval is what makes the playbook cite a real colleague's call rather
    # than inventing one, so a broken embedder is not a cosmetic failure.
    if settings.embeddings_is_live:
        try:
            # Two related sentences and one unrelated. A real embedder puts the
            # first two closer together; the hash-based twin has no idea, so
            # this distinguishes "answered" from "answered meaningfully".
            near, also_near, far = await providers.embeddings.embed([
                "your price is too high for our budget",
                "the cost is more than we can justify",
                "the implementation timeline works for us",
            ])
            dim = len(near)

            def cosine(a, b):
                return sum(x * y for x, y in zip(a, b))

            related, unrelated = cosine(near, also_near), cosine(near, far)
            if related > unrelated:
                line(
                    "embeddings", "live",
                    f"{dim}d via {settings.embedding_model} "
                    f"(related {related:.2f} > unrelated {unrelated:.2f})",
                )
            else:
                line(
                    "embeddings", "broken",
                    f"not semantic: related {related:.2f} <= unrelated {unrelated:.2f}",
                )
                failures.append("embeddings")
        except Exception as exc:  # noqa: BLE001
            line("embeddings", "broken", f"{type(exc).__name__}: {exc}"[:110])
            failures.append("embeddings")
    else:
        # Say which half is missing. "Set an embedding model" is unhelpful and
        # slightly insulting when the model is set and the key is not.
        if settings.llm_model_embedding and not settings.llm_key:
            why = f"{settings.llm_model_embedding} is configured; waiting for SALIX_LLM_API_KEY"
        elif settings.llm_key and not settings.llm_model_embedding:
            why = "set SALIX_LLM_MODEL_EMBEDDING to a model on this endpoint"
        else:
            why = "set DASHSCOPE_API_KEY, or an endpoint plus SALIX_LLM_MODEL_EMBEDDING"
        line("embeddings", "offline", why)

    # --- transcription -----------------------------------------------------
    # Actually called, unlike the others below, because this is the capability
    # people most often believe they have configured and have not -- and the
    # failure surfaces at the end of a long upload rather than here.
    if settings.deepgram_api_key:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                probe = await client.get(
                    "https://api.deepgram.com/v1/projects",
                    headers={"Authorization": f"Token {settings.deepgram_api_key}"},
                )
            if probe.status_code == 200:
                line("transcription", "live",
                     f"{settings.deepgram_model} via deepgram, diarization on")
            elif probe.status_code in (401, 403):
                line("transcription", "broken", "deepgram rejected the key")
                failures.append("transcription")
            else:
                line("transcription", "broken", f"deepgram {probe.status_code}")
                failures.append("transcription")
        except Exception as exc:  # noqa: BLE001
            line("transcription", "broken", f"{type(exc).__name__}: {exc}"[:110])
            failures.append("transcription")
    elif settings.dashscope_is_live:
        line("transcription", "live", f"{settings.model_asr_file} (not called)")
    else:
        line("transcription", "offline",
             "set SALIX_DEEPGRAM_API_KEY -- uploads are stored, not transcribed")

    # --- speech ------------------------------------------------------------
    # Not called: it costs a synthesis, and the Dojo's own voice comes from
    # edge-tts, which needs no key at all.
    if settings.dashscope_is_live:
        line("speech", "live", f"{settings.model_tts} (not called)")
    else:
        line("speech", "offline", "edge-tts covers the Dojo; this is Qwen TTS only")

    print()

    if failures:
        named = failures[0] if len(failures) == 1 else (
            " and ".join([", ".join(failures[:-1]), failures[-1]])
        )
        print(f"  {RED}A key is configured for {named}, and it did not work.{OFF}")
        print("  The error above is the upstream's own. Most often it is a")
        print("  mistyped key, an exhausted free quota, or a region mismatch")
        print("  between the key and SALIX_DASHSCOPE_REGION.")
        print()
        return 1

    if providers.mode == "mock":
        print(f"  {YELLOW}Everything is running on the offline twins.{OFF}")
        print("  The app is complete and nothing is stubbed out, but the")
        print("  analysis is scripted rather than inferred. Set a key in .env")
        print("  and run this again.")
        print()
        return 0

    if not settings.asr_is_live:
        print(f"  {YELLOW}Uploading a real recording still uses the offline twin.{OFF}")
        print("  The audio is stored and never listened to; a stand-in")
        print("  conversation is analysed in its place, and the upload page")
        print("  says so before you drop a file.")
        print()
        print("  Deepgram closes this: $200 of credit, no payment card, and")
        print("  Nova-3 does Urdu with speaker separation.")
        print("    https://console.deepgram.com  ->  SALIX_DEEPGRAM_API_KEY")
        print()

    print(f"  {GREEN}Ready.{OFF} Restart the API and the sidebar badge will follow.")
    print("  Re-seed to rebuild the corpus through the live path:")
    print("    python -m seed.build --reset --report")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
