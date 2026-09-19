"""Exponential backoff + simple circuit breaker."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.4,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except exceptions as exc:
            last = exc
            if i == attempts - 1:
                break
            time.sleep(base_delay * (2**i))
    assert last is not None
    raise last


class CircuitBreaker:
    def __init__(self, fail_max: int = 3, reset_timeout: float = 30.0) -> None:
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.open_until = 0.0

    def allow(self) -> bool:
        return time.time() >= self.open_until

    def record_success(self) -> None:
        self.failures = 0
        self.open_until = 0.0

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.fail_max:
            self.open_until = time.time() + self.reset_timeout
