"""Keep answering when one model does not.

Free tiers refuse under load: during testing Gemini returned 429 and 503 "high
demand" in the middle of a single call's analysis, which cost that call its reading
and its coaching plan. So reasoning runs through an ordered list of routes: other
models on the same key, then optionally another provider entirely. Different models
have different capacity, and a different vendor has a different outage.

A route that fails is rested briefly, so the next request does not spend its time
retrying something already known to be down. If everything fails the error still
surfaces, and the pipeline degrades as it always has. It never falls back to the
offline twin: made-up analysis presented as real is worse than an honest failure.

A stream can only move before its first token. After that the buyer has started
speaking, and a second voice taking over mid-sentence would be nonsense.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from ..config import Settings
from .base import ProviderError
from .dashscope_llm import DashScopeLLM

log = logging.getLogger("salix.llm.failover")

#: How long a route that just failed is passed over, in seconds.
REST_S = 45.0


@dataclass
class Route:
    label: str
    llm: Any
    resting_until: float = field(default=0.0)


def build_routes(settings: Settings) -> list[Route]:
    """Primary first, then its sibling models, then the backup provider's models."""
    routes = [Route(f"{settings.llm_provider_name}/{settings.deep_model}", DashScopeLLM(settings))]

    def add(base_url: Optional[str], key: Optional[str], model: str, cap: Optional[int] = None) -> None:
        copy = settings.model_copy(
            update={
                "llm_base_url": base_url,
                "llm_api_key": key,
                "llm_model_deep": model,
                "llm_model_fast": model,
                # The next route is the retry. Waiting here only delays it.
                "max_retries": 1,
                "llm_max_tokens_cap": cap,
            }
        )
        routes.append(Route(f"{copy.llm_provider_name}/{model}", DashScopeLLM(copy)))

    for model in settings.llm_fallback_list:
        add(settings.llm_endpoint, settings.llm_key, model)
    if settings.llm_backup_base_url and settings.llm_backup_api_key:
        for model in settings.llm_backup_list:
            add(settings.llm_backup_base_url, settings.llm_backup_api_key, model, settings.llm_backup_max_tokens)
    return routes


class FailoverLLM:
    def __init__(self, routes: list[Route]):
        self.routes = routes
        self.name = routes[0].llm.name

    def _order(self) -> list[Route]:
        """Rested routes last, not removed: if everything has failed recently, one
        of them may have recovered, and trying beats refusing."""
        now = time.monotonic()
        return sorted(self.routes, key=lambda r: r.resting_until > now)

    def _failed(self, route: Route, exc: Exception) -> None:
        route.resting_until = time.monotonic() + REST_S
        log.warning("%s failed (%s); trying the next route", route.label, str(exc)[:160])

    async def _first_answer(self, method: str, model: Optional[str], **kwargs: Any) -> Any:
        last: Optional[Exception] = None
        for route in self._order():
            try:
                # A caller's explicit model only means something on the primary.
                chosen = model if route is self.routes[0] else None
                return await getattr(route.llm, method)(model=chosen, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last = exc
                self._failed(route, exc)
        if isinstance(last, ProviderError):
            raise last
        raise ProviderError(self.name, f"every route failed: {last}", retryable=True)

    async def complete(self, *, model: Optional[str] = None, **kwargs: Any) -> str:
        return await self._first_answer("complete", model, **kwargs)

    async def structured(self, *, model: Optional[str] = None, **kwargs: Any) -> Any:
        return await self._first_answer("structured", model, **kwargs)

    async def stream(self, *, model: Optional[str] = None, **kwargs: Any) -> AsyncIterator[str]:
        last: Optional[Exception] = None
        for route in self._order():
            started = False
            try:
                chosen = model if route is self.routes[0] else None
                async for token in route.llm.stream(model=chosen, **kwargs):
                    started = True
                    yield token
                return
            except Exception as exc:  # noqa: BLE001
                if started:
                    raise
                last = exc
                self._failed(route, exc)
        if isinstance(last, ProviderError):
            raise last
        raise ProviderError(self.name, f"every route failed: {last}", retryable=True)


def build_llm(settings: Settings) -> Any:
    routes = build_routes(settings)
    if len(routes) == 1:
        return routes[0].llm
    log.info("reasoning routes: %s", " -> ".join(r.label for r in routes))
    return FailoverLLM(routes)
