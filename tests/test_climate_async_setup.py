"""Tests for async-safe climate setup path."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from custom_components.easyir.climate import async_setup_entry


class _FakeEntry:
    def __init__(self) -> None:
        self.data = {
            "entry_kind": "remote",
            "hub_entry_id": "hub-1",
            "hub_ids": ["hub-1"],
            "profile_path": "/tmp/profile.json",
        }
        self.entry_id = "entry-1"
        self.title = "Remote demo"


class _FakeHass:
    def __init__(self) -> None:
        self.async_add_executor_job = AsyncMock(
            return_value={
                "protocol": "legacy_profile",
                "pilot": False,
            }
        )
        hub = type(
            "HubEntry",
            (),
            {
                "entry_id": "hub-1",
                "title": "Hub",
                "data": {
                    "entry_kind": "hub",
                    "ieee": "aa:bb:cc:dd",
                    "endpoint_id": 1,
                    "transport": "ts1201_zha",
                },
            },
        )()
        self.config_entries = type(
            "Cfg",
            (),
            {"async_entries": lambda _self, _domain: [hub]},
        )()


class TestClimateAsyncSetup(unittest.IsolatedAsyncioTestCase):
    async def test_setup_entry_resolves_capability_view_in_executor(self) -> None:
        hass = _FakeHass()
        entry = _FakeEntry()
        added: list[object] = []

        def _add_entities(entities, _update_before_add) -> None:
            added.extend(entities)

        with patch("custom_components.easyir.climate.climate_capability_view") as cap_fn:
            await async_setup_entry(hass, entry, _add_entities)

        hass.async_add_executor_job.assert_awaited_once()
        call = hass.async_add_executor_job.await_args
        self.assertIs(call.args[0], cap_fn)
        self.assertEqual(call.args[1], "/tmp/profile.json")
        self.assertEqual(len(added), 1)


if __name__ == "__main__":
    unittest.main()
