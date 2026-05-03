from __future__ import annotations

import copy
import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Callable, Generic, Protocol, TypeVar

from backend.observability.logger import log_structured

T = TypeVar("T")


class CacheBackend(Protocol[T]):
    def get(self, key: str) -> tuple[bool, T | None]:
        ...

    def set(self, key: str, value: T) -> None:
        ...

    def get_or_compute(self, key: str, factory: Callable[[], T]) -> tuple[T, bool]:
        ...


@dataclass
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    """Small in-memory TTL cache for hot-path backend calls."""

    def __init__(self, name: str, ttl_seconds: int, max_size: int = 128) -> None:
        self._name = name
        self._ttl_seconds = max(1, ttl_seconds)
        self._max_size = max(1, max_size)
        self._entries: dict[str, _CacheEntry[T]] = {}
        self._inflight: dict[str, threading.Event] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _clone(value: T) -> T:
        return copy.deepcopy(value)

    def _prune(self, now: float) -> None:
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)

        while len(self._entries) > self._max_size:
            oldest_key = next(iter(self._entries))
            self._entries.pop(oldest_key, None)

    def get(self, key: str) -> tuple[bool, T | None]:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            entry = self._entries.get(key)
            if entry is None:
                return False, None
            return True, self._clone(entry.value)

    def set(self, key: str, value: T) -> None:
        now = time.monotonic()
        with self._lock:
            self._entries[key] = _CacheEntry(
                value=self._clone(value),
                expires_at=now + self._ttl_seconds,
            )
            self._prune(now)

    def get_or_compute(self, key: str, factory: Callable[[], T]) -> tuple[T, bool]:
        while True:
            now = time.monotonic()
            with self._lock:
                self._prune(now)
                entry = self._entries.get(key)
                if entry is not None:
                    log_structured("INFO", "cache_hit", cache=self._name, key=key[:16])
                    return self._clone(entry.value), True

                in_flight = self._inflight.get(key)
                if in_flight is None:
                    in_flight = threading.Event()
                    self._inflight[key] = in_flight
                    break

            log_structured("INFO", "cache_wait", cache=self._name, key=key[:16])
            in_flight.wait()

        log_structured("INFO", "cache_miss", cache=self._name, key=key[:16])
        try:
            value = factory()
            self.set(key, value)
            return self._clone(value), False
        finally:
            with self._lock:
                event = self._inflight.pop(key, None)
                if event is not None:
                    event.set()


def build_cache_key(*parts: object) -> str:
    raw = "||".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RedisCacheBackend(Generic[T]):
    """Placeholder interface for a future distributed cache backend."""

    def __init__(self, name: str, ttl_seconds: int, max_size: int = 128) -> None:
        raise NotImplementedError(
            "Redis cache backend is not implemented yet. "
            "Use CACHE_BACKEND=memory until a distributed backend is wired in."
        )


def build_cache_backend(
    kind: str,
    *,
    name: str,
    ttl_seconds: int,
    max_size: int = 128,
) -> CacheBackend[T]:
    normalized = str(kind or "memory").strip().lower()
    if normalized == "memory":
        return TTLCache(name, ttl_seconds, max_size=max_size)
    if normalized == "redis":
        return RedisCacheBackend(name, ttl_seconds, max_size=max_size)
    raise ValueError(f"Unsupported cache backend: {kind}")
