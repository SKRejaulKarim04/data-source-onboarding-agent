"""Retry with exponential backoff and full jitter.

Deliberately hand-rolled rather than pulled from tenacity: this is one of the
enterprise standards the static validator checks for, so it needs to be small
enough to read in the generated-code review screen.

Only :class:`TransientConnectionError` is retried. Authentication failures and
query errors fail immediately — retrying a wrong password just locks the account.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

from .exceptions import TransientConnectionError

T = TypeVar("T")

logger = logging.getLogger(__name__)


def retry_on_transient(
    max_attempts: int = 3,
    backoff_seconds: float = 0.5,
    max_backoff_seconds: float = 10.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry the wrapped callable when it raises a transient connection error.

    Args:
        max_attempts: Total attempts including the first. Must be >= 1.
        backoff_seconds: Base delay; attempt *n* waits up to ``base * 2**(n-1)``.
        max_backoff_seconds: Ceiling on any single sleep.

    Returns:
        A decorator preserving the wrapped function's signature.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error: TransientConnectionError | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except TransientConnectionError as exc:
                    last_error = exc
                    if attempt == max_attempts:
                        break
                    ceiling = min(backoff_seconds * (2 ** (attempt - 1)), max_backoff_seconds)
                    delay = random.uniform(0, ceiling)  # noqa: S311 - not crypto
                    logger.warning(
                        "Transient failure in %s (attempt %d/%d), retrying in %.2fs: %s",
                        func.__qualname__,
                        attempt,
                        max_attempts,
                        delay,
                        exc,
                    )
                    time.sleep(delay)

            assert last_error is not None
            raise TransientConnectionError(
                f"{func.__qualname__} failed after {max_attempts} attempts: "
                f"{last_error.message}",
                attempts=max_attempts,
                **last_error.context,
            ) from last_error

        return wrapper

    return decorator
