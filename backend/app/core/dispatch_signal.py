"""In-process wake-up signal for newly due Messages dispatches.

The database remains the source of truth and the periodic sweep remains the
recovery mechanism.  This event only removes the normal-case latency between
committing a due message and the next sweep.  A single scheduled-dispatch
worker consumes the signal, preserving the existing concurrency and
one-run-per-agent guards in ``run_scheduled_dispatch_pass``.
"""

from __future__ import annotations

import asyncio


_scheduled_dispatch_event = asyncio.Event()


def wake_scheduled_dispatch() -> None:
    """Wake the dispatch worker after a due message has committed."""
    _scheduled_dispatch_event.set()


async def wait_for_scheduled_dispatch(timeout_seconds: float) -> bool:
    """Wait for new work, falling back to the periodic recovery timeout.

    Returns ``True`` for an explicit wake and ``False`` for a timeout.  The
    event is cleared only after it has been consumed, so a signal arriving
    between the database pass and this wait is not lost.
    """
    try:
        await asyncio.wait_for(_scheduled_dispatch_event.wait(), timeout=timeout_seconds)
    except TimeoutError:
        return False
    _scheduled_dispatch_event.clear()
    return True


def reset_scheduled_dispatch_signal() -> None:
    """Leave no stale wake behind across app lifespan/test restarts."""
    _scheduled_dispatch_event.clear()
