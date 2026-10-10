import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")
logger = logging.getLogger("retry")


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    attempts: int = 3,
    base_delay: float = 0.2,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Exponential backoff (base, 2x, 4x...). Re-raises the last error when attempts run out."""
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001 - adapters raise varied transport errors
            if attempt == attempts:
                raise
            delay = base_delay * 2 ** (attempt - 1)
            logger.warning("retrying after %r (attempt %d/%d, sleep %.2fs)", exc, attempt, attempts, delay)
            await sleep(delay)
    raise RuntimeError("unreachable")
