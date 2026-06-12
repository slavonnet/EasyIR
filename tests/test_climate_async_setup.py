"""Tests for async-safe climate setup path."""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigSubentry

from custom_components.easyir.climate import async_setup_entry
from custom_components.easyir.const import SUBENTRY_TYPE_REMOTE


class TestClimateAsyncSetup(unittest.IsolatedAsyncioTestCase):
    async def test_setup_entry_resolves_capability_view_in_executor(self) -> None:
        parent = MagicMock()
        parent.version = 4
        parent.entry_id = "parent-1"
        parent.data = {}
        remote_sub = ConfigSubentry(
            data=MappingProxyType(
                {
                    "hub_subentry_id": "hub-1",
                    "hub_entry_id": "hub-1",
                    "hub_ids": ["hub-1"],
                    "profile_path": "/tmp/profile.json",
                }
            ),
            subentry_id="remote-1",
            subentry_type=SUBENTRY_TYPE_REMOTE,
            title="Remote demo",
            unique_id="hub-1_demo",
        )
        parent.subentries = MappingProxyType({"remote-1": remote_sub})

        hass = MagicMock()
        hass.async_add_executor_job = AsyncMock(
            return_value={
                "protocol": "legacy_profile",
                "pilot": False,
            }
        )
        hass.config_entries.async_entries.return_value = [parent]

        added: list[object] = []

        def _add_entities(entities, _update_before_add) -> None:
            added.extend(entities)

        with patch("custom_components.easyir.climate.climate_capability_view") as cap_fn:
            await async_setup_entry(hass, parent, _add_entities)

        hass.async_add_executor_job.assert_awaited_once()
        call = hass.async_add_executor_job.await_args
        self.assertIs(call.args[0], cap_fn)
        self.assertEqual(call.args[1], "/tmp/profile.json")
        self.assertEqual(len(added), 1)


if __name__ == "__main__":
    unittest.main()
