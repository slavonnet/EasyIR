"""Tests for room visibility policy and inbound decoded sync core."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

EASYIR_ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "easyir"
sys.path.insert(0, str(EASYIR_ROOT))

from signal_log.event_log import IrEventDirection, IrEventLog  # noqa: E402
from signal_log.room_policy import (  # noqa: E402
    entity_visible_for_ir_event,
    unknown_device_suggestion_allowed,
)
from signal_log.sync import SyncTarget, apply_inbound_decoded_signal  # noqa: E402


class TestRoomPolicy(unittest.TestCase):
    def test_same_room_required_when_event_has_room(self) -> None:
        self.assertTrue(
            entity_visible_for_ir_event(
                event_room_id="living",
                entity_area_id="living",
                hub_visible_room_ids=None,
            )
        )
        self.assertFalse(
            entity_visible_for_ir_event(
                event_room_id="living",
                entity_area_id="kitchen",
                hub_visible_room_ids=None,
            )
        )

    def test_hub_allow_list_denies_wrong_room_entity(self) -> None:
        rooms = frozenset({"living"})
        self.assertFalse(
            entity_visible_for_ir_event(
                event_room_id="living",
                entity_area_id="kitchen",
                hub_visible_room_ids=rooms,
            )
        )
        self.assertTrue(
            entity_visible_for_ir_event(
                event_room_id="living",
                entity_area_id="living",
                hub_visible_room_ids=rooms,
            )
        )

    def test_hub_allow_list_denies_unplaced_entity(self) -> None:
        rooms = frozenset({"living"})
        self.assertFalse(
            entity_visible_for_ir_event(
                event_room_id=None,
                entity_area_id=None,
                hub_visible_room_ids=rooms,
            )
        )

    def test_unknown_suggestion_blocked_under_hub_room_filter_without_event_room(
        self,
    ) -> None:
        rooms = frozenset({"living"})
        self.assertFalse(
            unknown_device_suggestion_allowed(
                event_room_id=None,
                hub_visible_room_ids=rooms,
            )
        )

    def test_unknown_suggestion_allowed_when_hub_unrestricted(self) -> None:
        self.assertTrue(
            unknown_device_suggestion_allowed(
                event_room_id=None,
                hub_visible_room_ids=None,
            )
        )


class TestInboundSync(unittest.TestCase):
    def test_no_cross_room_update(self) -> None:
        applied: list[str] = []

        def apply_decoded(entity_id: str, _decoded: dict) -> None:
            applied.append(entity_id)

        apply_inbound_decoded_signal(
            event_room_id="living",
            ieee="aa:bb",
            decoded_state={"hvac_mode": "cool"},
            decoded_device_id=None,
            targets=[
                SyncTarget("climate.a", "kitchen", "d1"),
                SyncTarget("climate.b", "living", "d2"),
            ],
            hub_visible_room_ids=None,
            apply_decoded=apply_decoded,
            event_log=None,
            suggest_unknown=None,
        )
        self.assertEqual(applied, ["climate.b"])

    def test_unknown_triggers_suggestion_when_allowed(self) -> None:
        suggestions: list[dict] = []

        apply_inbound_decoded_signal(
            event_room_id="living",
            ieee="aa:bb",
            decoded_state={"hvac_mode": "off"},
            decoded_device_id="unknown-dev",
            targets=[
                SyncTarget("climate.a", "living", "other"),
            ],
            hub_visible_room_ids=None,
            apply_decoded=lambda e, d: None,
            event_log=None,
            suggest_unknown=lambda p: suggestions.append(p),
        )
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["decoded_device_id"], "unknown-dev")

    def test_unknown_no_suggestion_when_hub_filtered_and_event_room_unknown(
        self,
    ) -> None:
        suggestions: list[dict] = []

        apply_inbound_decoded_signal(
            event_room_id=None,
            ieee="aa:bb",
            decoded_state={"hvac_mode": "off"},
            decoded_device_id=None,
            targets=[],
            hub_visible_room_ids=frozenset({"living"}),
            apply_decoded=lambda e, d: None,
            event_log=None,
            suggest_unknown=lambda p: suggestions.append(p),
        )
        self.assertEqual(suggestions, [])

    def test_inbound_logged(self) -> None:
        log = IrEventLog(max_events=10)
        apply_inbound_decoded_signal(
            event_room_id="living",
            ieee="x",
            decoded_state={"temperature": 22},
            decoded_device_id=None,
            targets=[
                SyncTarget("climate.a", "living", None),
            ],
            hub_visible_room_ids=None,
            apply_decoded=lambda e, d: None,
            event_log=log,
            suggest_unknown=None,
        )
        self.assertEqual(len(log), 1)
        ev = next(log.iter_events(limit=1))
        self.assertEqual(ev.direction, IrEventDirection.INBOUND)
        self.assertEqual(ev.room_id, "living")
        self.assertEqual(ev.decoded, {"temperature": 22})


if __name__ == "__main__":
    unittest.main()
