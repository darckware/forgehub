import asyncio

from app.core.dispatch_signal import (
    reset_scheduled_dispatch_signal,
    wait_for_scheduled_dispatch,
    wake_scheduled_dispatch,
)


async def test_explicit_signal_wakes_without_waiting_for_fallback_timeout():
    reset_scheduled_dispatch_signal()
    wake_scheduled_dispatch()

    assert await wait_for_scheduled_dispatch(10) is True
    assert await wait_for_scheduled_dispatch(0.01) is False


async def test_signal_arriving_while_worker_waits_is_consumed():
    reset_scheduled_dispatch_signal()

    waiter = asyncio.create_task(wait_for_scheduled_dispatch(10))
    await asyncio.sleep(0)
    wake_scheduled_dispatch()

    assert await waiter is True
