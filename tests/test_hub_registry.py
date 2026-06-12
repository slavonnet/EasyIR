"""Tests for hub-centric config entry helpers."""

from __future__ import annotations

import unittest

from custom_components.easyir.hub_registry import (
    entry_kind,
    hub_ids_for_remote,
    is_hub_entry,
    is_remote_entry,
)


class _Entry:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.entry_id = "entry-1"
        self.title = "Test"


class TestHubRegistry(unittest.TestCase):
    def test_hub_entry_kind(self) -> None:
        entry = _Entry({"entry_kind": "hub", "ieee": "aa:bb:cc"})
        self.assertTrue(is_hub_entry(entry))
        self.assertFalse(is_remote_entry(entry))

    def test_remote_entry_kind(self) -> None:
        entry = _Entry(
            {
                "entry_kind": "remote",
                "hub_entry_id": "hub-1",
                "profile_path": "/tmp/p.json",
            }
        )
        self.assertTrue(is_remote_entry(entry))
        self.assertEqual(hub_ids_for_remote(entry), ["hub-1"])

    def test_legacy_combined_entry_treated_as_remote(self) -> None:
        entry = _Entry(
            {
                "ieee": "aa:bb:cc",
                "profile_path": "/tmp/p.json",
                "endpoint_id": 1,
            }
        )
        self.assertEqual(entry_kind(entry), "remote")


if __name__ == "__main__":
    unittest.main()
