"""Normalized IR event log storage (inbound/outbound, room-scoped metadata)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterator


class IrEventDirection(str, Enum):
    """Whether the IR event was emitted by HA or received from the environment."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass(frozen=True, slots=True)
class IrEvent:
    """Room-scoped normalized log record for one IR-related event."""

    event_id: str
    direction: IrEventDirection
    recorded_at: datetime
    room_id: str | None
    ieee: str | None
    entity_id: str | None
    carrier_frequency_hz: int | None
    timings: list[int] | None
    repeat: int
    duty_cycle: float | None
    protocol_hint: str | None
    integrity_metadata: dict[str, Any]
    decoded: dict[str, Any] | None = None

    def matches_room(self, room_id: str | None) -> bool:
        """True if this event is in the given room scope (None matches only unscoped)."""
        if room_id is None:
            return self.room_id is None
        return self.room_id == room_id


class IrEventLog:
    """In-memory ring buffer of IR events (backend for future Signal Log UI)."""

    def __init__(self, max_events: int = 500) -> None:
        self._max_events = max(1, int(max_events))
        self._events: list[IrEvent] = []

    def append(self, event: IrEvent) -> None:
        """Append an event, evicting oldest when over capacity."""
        self._events.append(event)
        overflow = len(self._events) - self._max_events
        if overflow > 0:
            del self._events[0:overflow]

    def __len__(self) -> int:
        return len(self._events)

    def iter_events(
        self,
        *,
        room_id: str | None = None,
        direction: IrEventDirection | None = None,
        limit: int = 100,
    ) -> Iterator[IrEvent]:
        """Yield newest-first events optionally filtered by room and direction."""
        cap = max(0, int(limit))
        count = 0
        for ev in reversed(self._events):
            if room_id is not None and ev.room_id != room_id:
                continue
            if direction is not None and ev.direction != direction:
                continue
            yield ev
            count += 1
            if count >= cap:
                break


def new_event_id() -> str:
    """Return a unique id for log correlation."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Timezone-aware "now" for log timestamps."""
    return datetime.now(timezone.utc)


def build_outbound_event(
    *,
    room_id: str | None,
    ieee: str | None,
    entity_id: str | None,
    timings: list[int] | None,
    protocol_hint: str | None = None,
    carrier_frequency_hz: int | None = None,
    repeat: int = 1,
    duty_cycle: float | None = None,
    integrity_metadata: dict[str, Any] | None = None,
    decoded: dict[str, Any] | None = None,
) -> IrEvent:
    """Construct a normalized outbound IR log record."""
    return IrEvent(
        event_id=new_event_id(),
        direction=IrEventDirection.OUTBOUND,
        recorded_at=utcnow(),
        room_id=room_id,
        ieee=ieee,
        entity_id=entity_id,
        carrier_frequency_hz=carrier_frequency_hz,
        timings=timings,
        repeat=repeat,
        duty_cycle=duty_cycle,
        protocol_hint=protocol_hint,
        integrity_metadata=dict(integrity_metadata or {}),
        decoded=decoded,
    )


def build_inbound_event(
    *,
    room_id: str | None,
    ieee: str | None,
    timings: list[int] | None,
    protocol_hint: str | None = None,
    carrier_frequency_hz: int | None = None,
    repeat: int = 1,
    duty_cycle: float | None = None,
    integrity_metadata: dict[str, Any] | None = None,
    decoded: dict[str, Any] | None = None,
) -> IrEvent:
    """Construct a normalized inbound IR log record."""
    return IrEvent(
        event_id=new_event_id(),
        direction=IrEventDirection.INBOUND,
        recorded_at=utcnow(),
        room_id=room_id,
        ieee=ieee,
        entity_id=None,
        carrier_frequency_hz=carrier_frequency_hz,
        timings=timings,
        repeat=repeat,
        duty_cycle=duty_cycle,
        protocol_hint=protocol_hint,
        integrity_metadata=dict(integrity_metadata or {}),
        decoded=decoded,
    )
