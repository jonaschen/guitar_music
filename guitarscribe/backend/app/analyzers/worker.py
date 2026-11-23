"""Keep CPU inference off the API loop while retaining resources until it exits."""
import asyncio
from functools import partial


async def run_blocking_analysis(function, *args, **kwargs):
    task = asyncio.create_task(asyncio.to_thread(partial(function, *args, **kwargs)))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # A thread cannot be killed safely. Keep the pipeline's temporary audio
        # and concurrency slot alive until it stops reading/processing them.
        # Shutdown can cancel an already-cancelling request again. Shield every
        # wait so a second cancellation cannot abandon a still-running thread.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()  # retrieve a worker failure while preserving cancellation
        raise
