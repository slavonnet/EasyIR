"""Tests for async-safe climate setup path."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from custom_components.easyir.climate import async_setup_entry


class _FakeEntry:
    def __init__(self) -> None:
        self.data = {
            "ieee": "aa:bb:cc:dd",
            "profile_path": "/tmp/profile.json",
            "endpoint_id": 1,
        }
        self.entry_id = "entry-1"


class _FakeHass:
    def __init__(self) -> None:
        self.async_add_executor_job = AsyncMock(
            return_value={
                "protocol": "legacy_profile",
                "pilot": False,
            }
        )


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
