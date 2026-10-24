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
        try:
            await task
        except Exception:
            pass
        raise
