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


@pytest.mark.asyncio
async def test_repeated_cancellation_still_waits_for_worker_before_releasing_resources(tmp_path):
    entered, release = threading.Event(), threading.Event()
    source = tmp_path / 'source.wav'
    source.write_bytes(b'original audio')
    observed = []

    def inference():
        entered.set()
        assert release.wait(timeout=5)
        observed.append(source.read_bytes())

    async def pipeline():
        try:
            await run_blocking_analysis(inference)
        finally:
            source.unlink()

    task = asyncio.create_task(pipeline())
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(.02)
        task.cancel()  # e.g. application shutdown after a user cancellation
        await asyncio.sleep(.02)
        assert not task.done()
        assert source.is_file()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert observed == [b'original audio']
    assert not source.exists()
