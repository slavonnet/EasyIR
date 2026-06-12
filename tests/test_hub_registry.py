"""Tests for hub-centric config entry helpers."""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigSubentry

from custom_components.easyir.const import SUBENTRY_TYPE_HUB, SUBENTRY_TYPE_REMOTE
from custom_components.easyir.hub_registry import (
    HubRef,
    RemoteRef,
    hub_ids_for_remote_data,
    hub_subentry_data,
    is_hub_entry,
    is_remote_entry,
    iter_hub_refs,
    iter_remote_refs,
    remote_subentry_data,
)


class _Entry:
    def __init__(self, data: dict, *, version: int = 3, entry_id: str = "entry-1") -> None:
        self.data = data
        self.entry_id = entry_id
        self.title = "Test"
        self.version = version
        self.subentries = MappingProxyType({})


class TestHubRegistry(unittest.TestCase):
    def test_legacy_hub_entry_kind(self) -> None:
        entry = _Entry({"entry_kind": "hub", "ieee": "aa:bb:cc"})
        self.assertTrue(is_hub_entry(entry))
        self.assertFalse(is_remote_entry(entry))

    def test_legacy_remote_entry_kind(self) -> None:
        entry = _Entry(
            {
                "entry_kind": "remote",
                "hub_entry_id": "hub-1",
                "profile_path": "/tmp/p.json",
            }
        )
        self.assertTrue(is_remote_entry(entry))
        self.assertEqual(
            hub_ids_for_remote_data(entry.data),
            ["hub-1"],
        )

    def test_v4_subentry_hub_refs(self) -> None:
        parent = _Entry({}, version=4, entry_id="parent-1")
        hub_sub = ConfigSubentry(
            data=MappingProxyType(hub_subentry_data(ieee="aa:bb:cc:dd:ee:ff", endpoint_id=1)),
            subentry_id="hub-1",
            subentry_type=SUBENTRY_TYPE_HUB,
            title="Living Room Hub",
            unique_id="aabbccddeeff",
        )
        parent.subentries = MappingProxyType({"hub-1": hub_sub})
        hass = MagicMock()
        hass.config_entries.async_entries.return_value = [parent]
        hubs = iter_hub_refs(hass)
        self.assertEqual(len(hubs), 1)
        self.assertIsInstance(hubs[0], HubRef)
        self.assertEqual(hubs[0].subentry_id, "hub-1")

    def test_hub_subentry_data_includes_area(self) -> None:
        data = hub_subentry_data(
            ieee="aa:bb:cc:dd:ee:ff",
            endpoint_id=1,
            area_id="living_room",
        )
        self.assertEqual(data["area_id"], "living_room")

    def test_v4_subentry_remote_refs(self) -> None:
        parent = _Entry({}, version=4, entry_id="parent-1")
        remote_sub = ConfigSubentry(
            data=MappingProxyType(
                remote_subentry_data(
                    hub_subentry_id="hub-1",
                    profile_path="/tmp/ac.json",
                    remote_name="AC",
                )
            ),
            subentry_id="remote-1",
            subentry_type=SUBENTRY_TYPE_REMOTE,
            title="AC",
            unique_id="hub-1_ac",
        )
        parent.subentries = MappingProxyType({"remote-1": remote_sub})
        hass = MagicMock()
        hass.config_entries.async_entries.return_value = [parent]
        remotes = iter_remote_refs(hass)
        self.assertEqual(len(remotes), 1)
        self.assertIsInstance(remotes[0], RemoteRef)
        self.assertEqual(remotes[0].subentry_id, "remote-1")


if __name__ == "__main__":
    unittest.main()
