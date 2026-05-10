"""In-Memory Rate-Limiting per App.

Zwei Achsen:
1. Requests pro Minute (Sliding Window über letzten 60s)
2. Concurrent Requests (Semaphore-Counter)

Da der Router single-process läuft, reicht das. Bei Multi-Instance müsste man
auf Redis o.ä. umsteigen.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class _AppState:
    timestamps: deque[float] = field(default_factory=deque)
    in_flight: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RateLimiter:
    """Erlaubt: N RPM, M parallel pro App."""

    def __init__(self) -> None:
        self._states: dict[str, _AppState] = {}
        self._global_lock = asyncio.Lock()

    async def _state(self, app_id: str) -> _AppState:
        if app_id not in self._states:
            async with self._global_lock:
                if app_id not in self._states:
                    self._states[app_id] = _AppState()
        return self._states[app_id]

    async def acquire(self, app_id: str, rpm: int, max_concurrent: int) -> tuple[bool, int | None]:
        """Versuch Slot zu reservieren.

        Rückgabe: (allowed, retry_after_seconds_if_denied)
        Wenn allowed=True: Caller MUSS später ``release`` aufrufen.
        """
        state = await self._state(app_id)
        async with state.lock:
            now = time.monotonic()

            # 1. Sliding Window: alte Timestamps verwerfen
            cutoff = now - 60.0
            while state.timestamps and state.timestamps[0] < cutoff:
                state.timestamps.popleft()

            if rpm > 0 and len(state.timestamps) >= rpm:
                # Wann wird das älteste Event 60s alt? Dann wäre wieder Platz.
                oldest = state.timestamps[0]
                retry_after = max(1, int(60.0 - (now - oldest)) + 1)
                return False, retry_after

            if max_concurrent > 0 and state.in_flight >= max_concurrent:
                return False, 1  # kurzer Retry

            state.timestamps.append(now)
            state.in_flight += 1
            return True, None

    async def release(self, app_id: str) -> None:
        state = await self._state(app_id)
        async with state.lock:
            if state.in_flight > 0:
                state.in_flight -= 1

    def stats(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for app_id, state in self._states.items():
            out[app_id] = {
                "in_flight": state.in_flight,
                "last_minute": len(state.timestamps),
            }
        return out
