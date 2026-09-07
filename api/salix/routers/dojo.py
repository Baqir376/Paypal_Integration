"""The Dojo API.

Turn-by-turn over plain HTTP with SSE for the buyer's streaming reply, rather
than a persistent WebSocket. A practice session is naturally request-shaped --
the rep speaks, then waits -- and HTTP survives a flaky venue network, a page
reload and a proxy in a way a long-lived socket does not. For a feature whose
whole job is to work in front of an audience, that trade is worth making.

Speech in and out both run through Qwen: `/transcribe` posts the rep's recorded
turn to Qwen ASR, and `/speak` renders the buyer's line with Qwen TTS. The
browser's own speech APIs are the fallback when no key is configured, so the
Dojo is demonstrable either way.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import Field

from ..dojo.engine import DojoEngine
from ..dojo.persona import build_persona
from ..providers.base import ProviderError
from ..providers.edge_voice import MAX_CHARS as MAX_SPOKEN_CHARS
from ..providers.edge_voice import EdgeTTS
from ..schemas.common import SalixModel
from ..schemas.dojo import DojoSession
from ..store import repo
from .deps import OrgId, Prov, Session

log = logging.getLogger("salix.routers.dojo")

router = APIRouter(prefix="/dojo", tags=["dojo"])


class StartRequest(SalixModel):
    rep_id: str
    difficulty: int = 2
    scenario: str = ""
    #: "en" or "ur-roman". Anything else is treated as English.
    language: str = "en"


class TurnRequest(SalixModel):
    # Typed rather than `dict`: FastAPI then rejects a malformed session with a
    # 422 describing what is wrong, instead of the handler raising an
    # unhandled ValidationError and returning 500.
    session: DojoSession
    text: str = Field(default="", max_length=20000)
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, ge=0)


class EndRequest(SalixModel):
    session: DojoSession


@router.post("/start")
async def start_session(
    session: Session, org_id: OrgId, providers: Prov, body: StartRequest
) -> dict:
    """Build the persona from this rep's own failures and open a session."""
    rep = await repo.get_rep(session, body.rep_id)
    if rep is None:
        raise HTTPException(status_code=404, detail=f"No rep {body.rep_id}")

    persona = await build_persona(
        session, org_id, body.rep_id,
        difficulty=max(1, min(3, body.difficulty)),
        scenario_hint=body.scenario,
    )
    engine = DojoEngine(providers)
    dojo = engine.start(body.rep_id, persona, body.scenario, body.language)

    # The plays this rep has been prescribed drive the live coach rail.
    plan = await repo.get_coaching_plan(session, body.rep_id)
    prescribed = plan.prescribed_play_ids if plan else []
    plays = [
        p.model_dump(mode="json")
        for p in await repo.list_plays(session, org_id)
        if not prescribed or p.id in prescribed
    ]

    return {
        "session": dojo.model_dump(mode="json"),
        "rep_name": rep.name,
        "plays": plays[:6],
        "opening": _opening_line(persona, dojo.language),
    }


def _opening_line(persona, language: str = "en") -> str:
    """The buyer speaks first, so this sets the language before the model does.

    Hardcoded rather than generated: it costs a request, it is the same line
    every time, and a rep who opens a Roman Urdu session and is greeted in
    English has already been told the wrong thing about the exercise.
    """
    first = persona.name.split()[0]
    if language == "ur-roman":
        # "bol rahi", not "bol raha". Urdu verbs agree with the speaker's
        # gender, the buyer is always voiced by a woman, and the masculine
        # form under a female voice is the kind of mistake a Pakistani rep
        # notices in the first second and never stops noticing.
        return (
            f"Assalam-o-alaikum, {first} bol rahi hoon. Mere paas bees minute "
            "hain. Aap kya discuss karna chahte thay?"
        )
    return (
        f"Hi, {first} here. I have got about twenty minutes. "
        "What did you want to cover?"
    )


@router.post("/turn")
async def take_turn(providers: Prov, body: TurnRequest) -> StreamingResponse:
    """Stream the buyer's reply, then the coach nudges and updated session.

    The response is a single SSE stream carrying three event types so the
    client makes one request per turn: `delta` while the buyer speaks, then
    `nudge`s, then the authoritative `session` state.
    """
    # A turn with nothing in it is not a turn. The interface already refuses to
    # send one, but the endpoint accepted it and duly recorded silence as
    # something the rep said -- which then counted toward their turn count and
    # diluted their talk ratio.
    if not body.text.strip():
        raise HTTPException(
            status_code=422,
            detail="A turn needs something in it. Speak or type before sending.",
        )

    dojo = body.session.model_copy(deep=True)
    engine = DojoEngine(providers)

    engine.record_turn(dojo, "rep", body.text, body.start_ms, body.end_ms)

    async def generate():
        collected: list[str] = []
        try:
            async for token in engine.buyer_reply(dojo, body.text):
                collected.append(token)
                yield f"event: delta\ndata: {json.dumps({'text': token})}\n\n"
        except ProviderError as exc:
            log.warning("dojo buyer reply failed: %s", exc)

            # A rate limit is not the buyer being hard of hearing.
            #
            # Every failure used to become "Sorry, could you say that again?".
            # That is a reasonable thing for a buyer to say once, and a
            # catastrophe as a permanent state: with an exhausted free-tier
            # quota the rep gets it on every turn, forever, and concludes the
            # product is broken or stupid. The one cause they could actually
            # act on -- wait a moment, or raise the quota -- was the one thing
            # the fallback hid.
            #
            # So a limit is reported as a limit, on its own event, and the
            # buyer says nothing rather than saying something untrue.
            message = str(exc).lower()
            throttled = "429" in message or "quota" in message or "rate limit" in message

            if throttled:
                notice = {
                    "detail": (
                        "The model is rate limited right now. Wait a few "
                        "seconds and send that turn again."
                    ),
                    "retryable": True,
                }
                yield f"event: throttled\ndata: {json.dumps(notice)}\n\n"
                collected = []
            else:
                fallback = "Sorry, could you say that again?"
                collected = [fallback]
                yield f"event: delta\ndata: {json.dumps({'text': fallback})}\n\n"

        reply = "".join(collected).strip()
        if reply:
            engine.record_turn(dojo, "buyer", reply)

        for nudge in engine.nudges_for(dojo):
            yield f"event: nudge\ndata: {json.dumps(nudge.model_dump(mode='json'))}\n\n"

        yield (
            "event: session\n"
            f"data: {json.dumps(dojo.model_dump(mode='json'))}\n\n"
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/end")
async def end_session(
    session: Session, org_id: OrgId, providers: Prov, body: EndRequest
) -> dict:
    """Score the session on the same engine that scores real calls."""
    from datetime import datetime, timezone

    dojo = body.session.model_copy(deep=True)
    engine = DojoEngine(providers)

    plays = [p.model_dump(mode="json") for p in await repo.list_plays(session, org_id)]
    dojo.score = engine.score(dojo, plays)
    dojo.ended_at = datetime.now(timezone.utc).isoformat()

    await repo.put_dojo_session(session, org_id, dojo)
    await session.commit()

    log.info(
        "dojo session %s scored %.1f (%d/%d objections)",
        dojo.id, dojo.score.overall,
        dojo.score.objections_handled, dojo.score.objections_faced,
    )
    return dojo.model_dump(mode="json")


@router.post("/transcribe")
async def transcribe_turn(providers: Prov, file: UploadFile) -> dict:
    """Transcribe one recorded turn with Qwen ASR.

    Single speaker and a few seconds long, so diarization is off and the
    fast model is used.
    """
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio")

    from ..config import get_settings

    settings = get_settings()
    if not settings.is_live:
        raise HTTPException(
            status_code=503,
            detail="Speech recognition needs a Qwen API key. Use browser dictation.",
        )

    import base64

    try:
        result = await providers.asr.transcribe(
            f"data:audio/webm;base64,{base64.b64encode(audio).decode()}",
            diarize=False,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"text": " ".join(s.text for s in result.sentences)}


@router.get("/voice")
async def voice(text: str, lang: str = "") -> Response:
    """Free neural speech, in a woman's voice.

    Separate from /speak, which renders the buyer through Qwen TTS and needs a
    key. This one needs nothing, and it is the only path here that can say an
    Urdu sentence at all -- no Qwen TTS model supports Urdu, and Windows ships
    no Urdu voice unless somebody installs the language pack.

    A GET with the text in the query string, because the browser plays it by
    handing the URL to an <audio> element, and an <audio> element cannot POST.

    `lang` is the caller's own tag -- the one it hands to speech recognition --
    and the provider maps it to a voice. Passing `en-PK` for Roman Urdu used to
    fall through to the English voice, so the reply came back British.
    """
    line = (text or "").strip()
    if not line:
        raise HTTPException(status_code=422, detail="Nothing to say.")
    if len(line) > MAX_SPOKEN_CHARS:
        raise HTTPException(status_code=413, detail="Too long to speak in one go.")

    try:
        audio = await EdgeTTS().synthesize(line, language=lang)
    except ProviderError as exc:
        # Undocumented upstream; the client falls back to saying nothing.
        raise HTTPException(status_code=502, detail=str(exc))

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            # The same line is replayed whenever a session is scrolled back
            # through, and the text is the cache key by construction.
            "Cache-Control": "public, max-age=86400, immutable",
        },
    )


@router.post("/speak")
async def speak(providers: Prov, text: str, voice: str = "Jennifer") -> Response:
    """Render the buyer's line with Qwen TTS."""
    from ..config import get_settings

    if not get_settings().is_live:
        raise HTTPException(
            status_code=503,
            detail="Speech synthesis needs a Qwen API key. Use browser speech.",
        )
    try:
        audio = await providers.tts.synthesize(
            text[:1200], voice=voice, instruction="Natural business phone call."
        )
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return Response(content=audio, media_type="audio/mpeg")


@router.get("/sessions")
async def list_sessions(
    session: Session, org_id: OrgId, rep_id: str | None = None
) -> list[dict]:
    sessions = await repo.list_dojo_sessions(session, org_id, rep_id=rep_id)
    return [s.model_dump(mode="json") for s in sessions]
