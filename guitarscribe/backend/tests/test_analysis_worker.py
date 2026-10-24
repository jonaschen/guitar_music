import asyncio
import threading

import pytest

from app.analyzers.worker import run_blocking_analysis


@pytest.mark.asyncio
async def test_inference_keeps_api_loop_responsive_and_retains_slot_until_cancelled_worker_exits():
    entered, release = threading.Event(), threading.Event()

    def inference():
        entered.set()
        assert release.wait(timeout=5)
        return 42

    task = asyncio.create_task(run_blocking_analysis(inference))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        # This executes while inference is blocked, like a progress/cancel API.
        task.cancel()
        await asyncio.sleep(.02)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_inference_errors_are_not_silently_downgraded():
    def fail():
        raise ValueError('Unsupported timing')
    with pytest.raises(ValueError, match='Unsupported timing'):
        await run_blocking_analysis(fail)
