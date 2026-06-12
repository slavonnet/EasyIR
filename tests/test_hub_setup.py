"""Tests for hub setup helpers (offer remote flow, endpoint resolution)."""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.easyir import _async_offer_remote_setup
from custom_components.easyir.const import DOMAIN
from custom_components.easyir.endpoint import endpoint_for_ieee, endpoint_for_zha_device


class TestOfferRemoteSetup(unittest.IsolatedAsyncioTestCase):
    async def test_offer_remote_setup_updates_immutable_entry_data(self) -> None:
        entry = MagicMock()
        entry.data = MappingProxyType(
            {
                "entry_kind": "hub",
                "ieee": "aa:bb:cc:dd:ee:ff",
                "offer_remote_setup": True,
            }
        )

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        hass.config_entries.flow.async_init = AsyncMock()
        scheduled: list = []

        def _schedule_task(coro) -> None:
            scheduled.append(coro)

        hass.async_create_task = _schedule_task

        await _async_offer_remote_setup(hass, entry)
        self.assertEqual(len(scheduled), 1)
        await scheduled[0]

        hass.config_entries.async_update_entry.assert_called_once()
        update_call = hass.config_entries.async_update_entry.call_args
        updated_data = update_call.kwargs["data"]
        self.assertNotIn("offer_remote_setup", updated_data)
        self.assertEqual(updated_data["ieee"], "aa:bb:cc:dd:ee:ff")

        hass.config_entries.flow.async_init.assert_awaited_once()
        init_call = hass.config_entries.flow.async_init.await_args
        self.assertEqual(init_call.args[0], DOMAIN)
        self.assertEqual(
            init_call.kwargs["context"]["hub_entry_id"],
            entry.entry_id,
        )

    async def test_offer_remote_setup_skips_when_flag_missing(self) -> None:
        entry = MagicMock()
        entry.data = MappingProxyType({"entry_kind": "hub", "ieee": "aa:bb"})

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        hass.config_entries.flow.async_init = AsyncMock()

        await _async_offer_remote_setup(hass, entry)

        hass.config_entries.async_update_entry.assert_not_called()
        hass.config_entries.flow.async_init.assert_not_called()


class TestEndpointResolution(unittest.TestCase):
    def test_default_endpoint_for_zha_device(self) -> None:
        self.assertEqual(endpoint_for_zha_device(None), 1)

    def test_endpoint_for_ieee_without_device_registry(self) -> None:
        hass = MagicMock()
        reg = MagicMock()
        reg.devices = {}
        with patch(
            "custom_components.easyir.endpoint.dr.async_get",
            return_value=reg,
        ):
            self.assertEqual(endpoint_for_ieee(hass, "AA:BB:CC:DD:EE:FF"), 1)


if __name__ == "__main__":
    unittest.main()
