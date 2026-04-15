"""Room-aware IR signal log and scoped sync helpers."""

from .event_log import (
    IrEvent,
    IrEventDirection,
    IrEventLog,
    build_inbound_event,
    build_outbound_event,
    new_event_id,
    utcnow,
)
from .room_policy import (
    entity_visible_for_ir_event,
    hub_restricts_rooms,
    unknown_device_suggestion_allowed,
)
from .sync import SyncTarget, apply_inbound_decoded_signal

__all__ = [
    "IrEvent",
    "IrEventDirection",
    "IrEventLog",
    "SyncTarget",
    "apply_inbound_decoded_signal",
    "build_inbound_event",
    "build_outbound_event",
    "entity_visible_for_ir_event",
    "hub_restricts_rooms",
    "new_event_id",
    "unknown_device_suggestion_allowed",
    "utcnow",
]
