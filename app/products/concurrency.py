from __future__ import annotations

from contextlib import contextmanager
from threading import Lock
from typing import Iterator


class KeyedLockPool:
    """같은 상품 키의 프로세스 내 중복 수집을 직렬화한다."""

    def __init__(self) -> None:
        self._guard = Lock()
        self._locks: dict[str, Lock] = {}

    @contextmanager
    def acquire(self, key: str) -> Iterator[None]:
        with self._guard:
            lock = self._locks.setdefault(key, Lock())

        lock.acquire()
        try:
            yield
        finally:
            lock.release()
