"""The live progress stream has to outlast a slow stage."""

import asyncio
import json
from unittest.mock import patch

from salix.pipeline.bus import bus
from salix.routers import calls
from salix.schemas.pipeline import StageKey, StageStatus


def test_a_quiet_stage_does_not_end_the_stream():
    call_id = "call_quiet_stage"

    async def run_pipeline():
        await bus.emit(call_id, StageKey.TRANSCRIBE, StageStatus.RUNNING)
        await asyncio.sleep(0.2)  # several heartbeats with nothing to report
        await bus.emit(call_id, StageKey.DONE, StageStatus.OK)

    async def scenario():
        pipeline = asyncio.create_task(run_pipeline())
        frames = [frame async for frame in calls._pipeline_frames(call_id)]
        await pipeline
        return frames

    with patch.object(calls, "STREAM_KEEPALIVE_S", 0.03):
        frames = asyncio.run(scenario())

    stages = [json.loads(f[6:])["stage"] for f in frames if f.startswith("data: ")]
    assert stages == [StageKey.TRANSCRIBE.value, StageKey.DONE.value]
    assert any(f.startswith(": keepalive") for f in frames)
    assert frames[-1].startswith("event: close")
