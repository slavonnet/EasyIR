"""Inbound decoded signal -> room-scoped entity state sync (policy-enforced)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .event_log import IrEventLog, build_inbound_event
from .room_policy import entity_visible_for_ir_event, unknown_device_suggestion_allowed


@dataclass(frozen=True, slots=True)
class SyncTarget:
    """A virtual device that may receive decoded inbound state."""

    entity_id: str
    area_id: str | None
    device_id: str | None


UnknownSuggestion = dict[str, Any]
ApplyDecodedFn = Callable[[str, Mapping[str, Any]], None]
SuggestUnknownFn = Callable[[UnknownSuggestion], None]


def apply_inbound_decoded_signal(
    *,
    event_room_id: str | None,
    ieee: str | None,
    decoded_state: Mapping[str, Any],
    decoded_device_id: str | None,
    targets: list[SyncTarget],
    hub_visible_room_ids: frozenset[str] | None,
    apply_decoded: ApplyDecodedFn,
    event_log: IrEventLog | None = None,
    timings: list[int] | None = None,
    protocol_hint: str | None = None,
    suggest_unknown: SuggestUnknownFn | None = None,
    integrity_metadata: Mapping[str, Any] | None = None,
) -> list[str]:
    """
    Apply decoded inbound IR to eligible entities only (no cross-room updates).

    Returns list of entity_ids that were updated.
    """
    updated: list[str] = []
    matched = False

    for target in targets:
        if decoded_device_id is not None and target.device_id is not None:
            if target.device_id != decoded_device_id:
                continue
        elif decoded_device_id is not None:
            continue

        if not entity_visible_for_ir_event(
            event_room_id=event_room_id,
            entity_area_id=target.area_id,
            hub_visible_room_ids=hub_visible_room_ids,
        ):
            continue

        apply_decoded(target.entity_id, decoded_state)
        updated.append(target.entity_id)
        matched = True

    if event_log is not None:
        event_log.append(
            build_inbound_event(
                room_id=event_room_id,
                ieee=ieee,
                timings=timings,
                protocol_hint=protocol_hint,
                integrity_metadata={
                    "decoded_device_id": decoded_device_id,
                    "updated_entity_ids": list(updated),
                    "matched_known_device": matched,
                    **dict(integrity_metadata or {}),
                },
                decoded=dict(decoded_state),
            )
        )

    if (
        not matched
        and suggest_unknown is not None
        and unknown_device_suggestion_allowed(
            event_room_id=event_room_id,
            hub_visible_room_ids=hub_visible_room_ids,
        )
    ):
        suggest_unknown(
            {
                "event_room_id": event_room_id,
                "ieee": ieee,
                "decoded_state": dict(decoded_state),
                "decoded_device_id": decoded_device_id,
            }
        )

    return updated
