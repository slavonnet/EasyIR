"""Shared pooled service dispatcher with deduplication and send interval."""

from __future__ import annotations

import asyncio
import heapq
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from homeassistant.core import HomeAssistant

from .const import DOMAIN

DEFAULT_POOL_INTERVAL_S = 1.0
DATA_SERVICE_CALL_POOL = "service_call_pool"


@dataclass(slots=True)
class _QueuedCall:
    priority: int
    order: int
    ieee: str
    domain: str
    service: str
    data: dict[str, Any]
    return_response: bool
    dedupe_key: str | None
    waiters: list[asyncio.Future[Any]] = field(default_factory=list)


@dataclass(slots=True)
class _PoolState:
    queue: list[tuple[int, int, _QueuedCall]] = field(default_factory=list)
    pending_by_key: dict[str, _QueuedCall] = field(default_factory=dict)
    worker: asyncio.Task[None] | None = None
    last_sent_at: float = 0.0


def _canonical_payload_key(value: Any) -> str:
    """Build stable dedupe key for nested payloads."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except TypeError:
        return repr(value)


class ServiceCallPool:
    """Serialize and deduplicate outbound service calls across EasyIR."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        min_interval_s: float = DEFAULT_POOL_INTERVAL_S,
        monotonic: Callable[[], float] | None = None,
        sleeper: Callable[[float], Any] | None = None,
    ) -> None:
        self._hass = hass
        self._min_interval_s = max(0.0, float(min_interval_s))
        self._monotonic = monotonic or time.monotonic
        self._sleeper = sleeper or asyncio.sleep
        self._state = _PoolState()
        self._order = 0

    async def async_call(
        self,
        *,
        ieee: str,
        domain: str,
        service: str,
        data: dict[str, Any],
        return_response: bool = False,
        dedupe: bool = True,
        priority: int = 10,
    ) -> Any:
        """Enqueue service call into shared pool and await the result."""
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[Any] = loop.create_future()
        norm_ieee = str(ieee).strip().lower().replace(" ", "")
        key = None
        if dedupe:
            key = (
                f"{norm_ieee}|{domain}|{service}|{int(return_response)}|"
                f"{_canonical_payload_key(data)}"
            )
        state = self._state
        existing = state.pending_by_key.get(key) if key is not None else None
        if existing is not None:
            existing.waiters.append(waiter)
        else:
            self._order += 1
            queued = _QueuedCall(
                priority=int(priority),
                order=self._order,
                ieee=norm_ieee,
                domain=domain,
                service=service,
                data=dict(data),
                return_response=bool(return_response),
                dedupe_key=key,
                waiters=[waiter],
            )
            heapq.heappush(state.queue, (queued.priority, queued.order, queued))
            if key is not None:
                state.pending_by_key[key] = queued
            if state.worker is None or state.worker.done():
                state.worker = asyncio.create_task(self._run_worker(state))
        return await waiter

    async def _run_worker(self, state: _PoolState) -> None:
        while state.queue:
            _, _, queued = heapq.heappop(state.queue)
            now = self._monotonic()
            wait_s = self._min_interval_s - (now - state.last_sent_at)
            if wait_s > 0:
                await self._sleeper(wait_s)
            try:
                result = await self._hass.services.async_call(
                    queued.domain,
                    queued.service,
                    queued.data,
                    blocking=True,
                    return_response=queued.return_response,
                )
            except Exception as err:  # pragma: no cover - propagated to callers
                for waiter in queued.waiters:
                    if not waiter.done():
                        waiter.set_exception(err)
            else:
                for waiter in queued.waiters:
                    if not waiter.done():
                        waiter.set_result(result)
            finally:
                if queued.dedupe_key is not None:
                    state.pending_by_key.pop(queued.dedupe_key, None)
                state.last_sent_at = self._monotonic()
        state.worker = None


def get_service_call_pool(hass: HomeAssistant) -> ServiceCallPool:
    """Return shared pooled dispatcher for EasyIR service calls."""
    root = hass.data.setdefault(DOMAIN, {})
    pool = root.get(DATA_SERVICE_CALL_POOL)
    if isinstance(pool, ServiceCallPool):
        return pool
    interval = float(root.get("service_call_pool_interval_s", DEFAULT_POOL_INTERVAL_S))
    new_pool = ServiceCallPool(hass, min_interval_s=interval)
    root[DATA_SERVICE_CALL_POOL] = new_pool
    return new_pool


def build_service_call_dedupe_key(
    *,
    ieee: str,
    domain: str,
    service: str,
    data: dict[str, Any],
    return_response: bool,
) -> str:
    """Expose stable dedupe key builder for callers needing custom payload control."""
    norm_ieee = str(ieee).strip().lower().replace(" ", "")
    return (
        f"{norm_ieee}|{domain}|{service}|{int(return_response)}|{_canonical_payload_key(data)}"
    )


async def async_call_pooled_service(
    hass: HomeAssistant,
    *,
    ieee: str,
    domain: str,
    service: str,
    data: dict[str, Any],
    return_response: bool = False,
    dedupe: bool = True,
    priority: int = 10,
) -> Any:
    """Convenience wrapper around the shared per-IEEE call pool."""
    pool = get_service_call_pool(hass)
    return await pool.async_call(
        ieee=ieee,
        domain=domain,
        service=service,
        data=data,
        return_response=return_response,
        dedupe=dedupe,
        priority=priority,
    )
