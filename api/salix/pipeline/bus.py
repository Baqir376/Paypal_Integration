"""In-process event bus for live pipeline progress.

The ingest screen renders the analysis DAG as it runs, which needs events to
reach the browser the moment a stage changes. This is a small fan-out bus:
the pipeline publishes, one queue per subscriber receives, SSE drains it.

Two behaviours matter and are easy to get wrong:

* **Late subscribers see history.** The browser often connects a moment after
  the upload POST returns, so every event is replayed on subscribe. Without
  that, the first stages flash past unseen.
* **A slow consumer never blocks the pipeline.** Queues are bounded and drop
  their oldest event when full, so a backgrounded browser tab cannot stall
  analysis.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import AsyncIterator

from ..schemas.pipeline import (
    STAGE_AGENTS,
    STAGE_LABELS,
    PipelineEvent,
    StageKey,
    StageStatus,
)

log = logging.getLogger("salix.bus")

MAX_QUEUE = 256
MAX_HISTORY = 128


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[PipelineEvent]]] = defaultdict(list)
        self._history: dict[str, list[PipelineEvent]] = defaultdict(list)

    async def publish(self, event: PipelineEvent) -> None:
        history = self._history[event.call_id]
        history.append(event)
        if len(history) > MAX_HISTORY:
            del history[: len(history) - MAX_HISTORY]

        for queue in list(self._subscribers[event.call_id]):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop the oldest rather than the newest: a reconnecting client
                # cares far more about the current stage than the first one.
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    log.debug("dropping event for saturated subscriber")

    async def emit(
        self,
        call_id: str,
        stage: StageKey,
        status: StageStatus,
        *,
        detail: str = "",
        progress: float = 0.0,
        elapsed_ms: int = 0,
        payload: dict | None = None,
    ) -> None:
        await self.publish(
            PipelineEvent(
                call_id=call_id,
                stage=stage,
                status=status,
                label=STAGE_LABELS.get(stage, stage.value),
                agent=STAGE_AGENTS.get(stage, ""),
                detail=detail,
                progress=progress,
                elapsed_ms=elapsed_ms,
                payload=payload,
            )
        )

    async def subscribe(self, call_id: str) -> AsyncIterator[PipelineEvent]:
        """Yield past events, then live ones until the pipeline finishes."""
        queue: asyncio.Queue[PipelineEvent] = asyncio.Queue(maxsize=MAX_QUEUE)
        self._subscribers[call_id].append(queue)
        try:
            for event in list(self._history[call_id]):
                yield event
                if self._is_final(event):
                    return

            while True:
                event = await queue.get()
                yield event
                if self._is_final(event):
                    return
        finally:
            subscribers = self._subscribers.get(call_id, [])
            if queue in subscribers:
                subscribers.remove(queue)
            if not subscribers:
                self._subscribers.pop(call_id, None)

    @staticmethod
    def _is_final(event: PipelineEvent) -> bool:
        # Only the end. A failed stage is not one: anatomy can fail and the
        # graph carries on, and closing the stream there told the browser the
        # analysis was complete while it was still running. Every path through
        # the pipeline emits DONE, including the fatal ones.
        return event.stage is StageKey.DONE

    def history(self, call_id: str) -> list[PipelineEvent]:
        return list(self._history.get(call_id, []))

    def clear(self, call_id: str) -> None:
        self._history.pop(call_id, None)


bus = EventBus()
