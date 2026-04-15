"""Tests for inbound ZHA -> EasyIR Signal Log bridge."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from custom_components.easyir.signal_log.event_log import IrEventDirection
from custom_components.easyir.signal_log.ha_bridge import (
    async_handle_zha_event_for_easyir,
    get_domain_event_log,
)


class _FakeConfigEntries:
    def __init__(self, entries: list) -> None:
        self._entries = entries

    def async_entries(self, _domain: str) -> list:
        return list(self._entries)


class _FakeHass:
    def __init__(self, entries: list) -> None:
        self.config_entries = _FakeConfigEntries(entries)
        self.data = {}


class _FakeEntry:
    def __init__(self, ieee: str) -> None:
        self.data = {"ieee": ieee}


class TestSignalLogInboundBridge(unittest.TestCase):
    def test_ignores_non_ts1201_cluster(self) -> None:
        hass = _FakeHass([_FakeEntry("aa:bb:cc:dd")])
        ok = async_handle_zha_event_for_easyir(
            hass,
            {
                "device_ieee": "aa:bb:cc:dd",
                "cluster_id": 0x0006,
                "command": 2,
                "params": {"code": "AQID"},
            },
        )
        self.assertFalse(ok)
        self.assertEqual(len(get_domain_event_log(hass)), 0)

    def test_ignores_unconfigured_ieee(self) -> None:
        hass = _FakeHass([_FakeEntry("11:22:33:44")])
        ok = async_handle_zha_event_for_easyir(
            hass,
            {
                "device_ieee": "aa:bb:cc:dd",
                "cluster_id": 0xE004,
                "command": 1,
                "params": {"code": "AQID"},
            },
        )
        self.assertFalse(ok)
        self.assertEqual(len(get_domain_event_log(hass)), 0)

    def test_appends_inbound_event_when_payload_decodes(self) -> None:
        hass = _FakeHass([_FakeEntry("aa:bb:cc:dd")])
        with patch(
            "custom_components.easyir.signal_log.ha_bridge.decode_ir_payload_auto",
            return_value=type(
                "Decoded",
                (),
                {
                    "raw_timings": [9000, -4500, 560, -560],
                    "source_encoding": "tuya_base64",
                },
            )(),
        ), patch(
            "custom_components.easyir.signal_log.ha_bridge.resolve_ieee_primary_area_id",
            return_value="living_room",
        ):
            ok = async_handle_zha_event_for_easyir(
                hass,
                {
                    "device_ieee": "aa:bb:cc:dd",
                    "cluster_id": 0xE004,
                    "command": 1,
                    "params": {"code": "AQID"},
                },
            )
        self.assertTrue(ok)
        log = get_domain_event_log(hass)
        self.assertEqual(len(log), 1)
        ev = next(log.iter_events(limit=1))
        self.assertEqual(ev.direction, IrEventDirection.INBOUND)
        self.assertEqual(ev.ieee, "aa:bb:cc:dd")
        self.assertEqual(ev.room_id, "living_room")
        self.assertEqual(ev.protocol_hint, "tuya_base64")
        self.assertEqual(ev.timings, [9000, -4500, 560, -560])
        self.assertEqual(ev.integrity_metadata.get("source"), "zha_event")


if __name__ == "__main__":
    unittest.main()
