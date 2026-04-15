"""Room visibility policy for IR log, sync, and assistant hooks."""

from __future__ import annotations

from typing import AbstractSet


def hub_restricts_rooms(hub_visible_room_ids: AbstractSet[str] | None) -> bool:
    """True when the hub is configured with an explicit non-empty room allow-list."""
    if hub_visible_room_ids is None:
        return False
    return len(hub_visible_room_ids) > 0


def entity_allowed_by_hub_rooms(
    entity_area_id: str | None,
    hub_visible_room_ids: AbstractSet[str] | None,
) -> bool:
    """Whether an entity may participate for this hub given hub room allow-list."""
    if not hub_restricts_rooms(hub_visible_room_ids):
        return True
    if entity_area_id is None:
        return False
    assert hub_visible_room_ids is not None
    return entity_area_id in hub_visible_room_ids


def is_same_room(event_room_id: str | None, entity_area_id: str | None) -> bool:
    """Strict same-room check; unknown placement does not match a concrete event room."""
    if event_room_id is None:
        return True
    if entity_area_id is None:
        return False
    return entity_area_id == event_room_id


def entity_visible_for_ir_event(
    *,
    event_room_id: str | None,
    entity_area_id: str | None,
    hub_visible_room_ids: AbstractSet[str] | None,
) -> bool:
    """
    Eligibility for inbound sync / logging side effects for one virtual device.

    Blocks cross-room updates: when the event carries a room, the entity must
    report the same area. Hub room allow-lists further restrict which entities
    belong to the hub scope.
    """
    if not entity_allowed_by_hub_rooms(entity_area_id, hub_visible_room_ids):
        return False
    return is_same_room(event_room_id, entity_area_id)


def unknown_device_suggestion_allowed(
    *,
    event_room_id: str | None,
    hub_visible_room_ids: AbstractSet[str] | None,
) -> bool:
    """
    Whether to surface an add-device suggestion for an unknown decoded signal.

    When the hub is room-restricted, only suggest if the event room is known and
    allowed for the hub. When the event has no room, do not suggest if the hub
    uses a room filter (cannot prove visibility).
    """
    if not hub_restricts_rooms(hub_visible_room_ids):
        return True
    assert hub_visible_room_ids is not None
    if event_room_id is None:
        return False
    return event_room_id in hub_visible_room_ids
