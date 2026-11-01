"""Health, org and cross-cutting reads."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..metrics import analytics
from ..schemas.common import SalixModel
from ..store import repo
from .deps import OrgId, Prov, Session

router = APIRouter(tags=["meta"])


class Health(SalixModel):
    status: str
    provider_mode: str
    models: dict[str, str]
    # Which service is actually behind each capability. A mixed setup is now
    # possible -- a Gemini key drives the reasoning while transcription stays
    # on the offline twin -- and one "live" badge for all four would be a lie.
    providers: dict[str, str] = {}
    seeded: bool
    calls: int
    plays: int
    moments: int


@router.get("/health", response_model=Health)
async def health(session: Session, providers: Prov) -> Health:
    """Liveness plus enough state for the UI to explain itself.

    The frontend shows a mode badge -- live or offline -- because a judge
    should never have to wonder whether they are looking at real inference.
    """
    settings = get_settings()
    org = await repo.first_org(session)

    calls = plays = moments = 0
    # Public, so with accounts on it says nothing about anybody's data.
    if org is not None and not settings.auth_required:
        calls = len(await repo.list_calls(session, org.id, limit=1000))
        plays = len(await repo.list_plays(session, org.id))
        moments = await repo.count_moments(session, org.id)

    llm_live = settings.llm_is_live
    native_live = settings.dashscope_is_live
    offline = "offline twin"

    return Health(
        status="ok",
        provider_mode=providers.mode,
        models={
            # The resolved names, not the configured defaults: with an
            # override in place these are the models actually being called.
            "reasoning": settings.deep_model,
            "fast": settings.fast_model,
            # The model that would actually be called, which is no longer
            # always DashScope's.
            "transcription": settings.asr_model,
            "realtime_asr": settings.model_asr_realtime,
            # The resolved one. `model_embedding` is the DashScope default and
            # stays set even when embeddings are being served by somebody else,
            # so reporting it named a model that was never called.
            "embedding": settings.embedding_model,
            "speech": settings.model_tts,
        },
        providers={
            "reasoning": settings.llm_provider_name if llm_live else offline,
            # Transcription has its own credential now: Deepgram takes the
            # audio in the request body, so it works where Model Studio -- which
            # fetches the file itself -- needs a reachable URL.
            "transcription": settings.asr_provider_name,
            # Embeddings follow their own credential: `embeddings.create` is
            # part of the OpenAI protocol, so any compatible endpoint can serve
            # them even when DashScope is absent. Reporting them as offline
            # because DashScope is missing tells the badge a lie.
            "embedding": (
                ("alibaba model studio" if settings.dashscope_api_key else settings.llm_provider_name)
                if settings.embeddings_is_live
                else offline
            ),
            "speech": "alibaba model studio" if native_live else offline,
        },
        seeded=org is not None and calls > 0,
        calls=calls,
        plays=plays,
        moments=moments,
    )


@router.get("/ready")
async def ready(session: Session) -> JSONResponse:
    """Can this process actually serve a request right now?

    Distinct from /health on purpose. Health says the process is alive, which
    a deployment platform uses to decide whether to restart it; readiness says
    the database answers, which is what decides whether to send traffic. A
    process whose database has gone away is alive and must not be given work.

    Deliberately cheap: one round trip, no inference, no counting. A readiness
    probe that costs anything gets run every few seconds forever.
    """
    from sqlalchemy import text as sql_text

    try:
        await session.execute(sql_text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        # 503, not 500: this is "not yet" rather than "broken", and that is
        # the difference between a load balancer waiting and a page alerting.
        return JSONResponse(
            status_code=503,
            content={"ready": False, "detail": f"database unreachable: {type(exc).__name__}"},
        )
    return JSONResponse(status_code=200, content={"ready": True})


class Overview(SalixModel):
    """Everything the command centre needs, in one request."""

    org: dict
    team: dict
    reps: list[dict]
    recent_calls: list[dict]
    risks: list[dict]
    top_plays: list[dict]


@router.get("/overview", response_model=Overview)
async def overview(session: Session, org_id: OrgId, providers: Prov) -> Overview:
    from ..agents.analyst import Analyst

    org = await repo.get_org(session, org_id)
    deals = await repo.list_deals(session, org_id)
    bundles = await analytics.load_bundles(session, org_id)
    snapshots = await analytics.rep_snapshots(session, org_id)
    plays = await repo.list_plays(session, org_id)

    team = analytics.team_metrics(bundles, deals)

    # The risk radar is derived, not stored, so it is always current with the
    # latest call rather than with the last report generation.
    analyst = Analyst(providers)
    risks = await analyst.portfolio_risks(session, deals, snapshots)

    recent = sorted(bundles, key=lambda b: b.call.occurred_at, reverse=True)[:8]
    rep_names = {s.rep.id: s.rep.name for s in snapshots}

    return Overview(
        org=org.model_dump(mode="json") if org else {},
        team=team.model_dump(mode="json"),
        reps=[s.model_dump(mode="json") for s in snapshots],
        recent_calls=[
            {
                **b.call.model_dump(mode="json"),
                "rep_name": rep_names.get(b.call.rep_id, ""),
                "score": b.scorecard.overall if b.scorecard else None,
                "talk_ratio_rep": b.metrics.talk_ratio_rep if b.metrics else None,
                "headline": b.analysis.headline if b.analysis else "",
            }
            for b in recent
        ],
        risks=[r.model_dump(mode="json") for r in risks[:8]],
        top_plays=[
            p.model_dump(mode="json")
            for p in sorted(plays, key=lambda p: -p.usage_count)[:6]
        ],
    )


class SearchHit(SalixModel):
    moment: dict
    score: float


@router.get("/search", response_model=list[SearchHit])
async def search(
    session: Session,
    org_id: OrgId,
    providers: Prov,
    q: str,
    kind: str | None = None,
    outcome: str | None = None,
    k: int = 8,
) -> list[SearchHit]:
    """Semantic search across every indexed conversational moment.

    This is the retrieval layer the Coach uses, exposed directly -- ask "how
    did anyone handle a pricing objection" and get the passages back.
    """
    if not q.strip():
        return []
    embedding = (await providers.embeddings.embed([q]))[0]
    results = await repo.search_moments(
        session, org_id, embedding, kind=kind, outcome=outcome, k=k
    )
    return [SearchHit(moment=m, score=round(s, 4)) for m, s in results]
