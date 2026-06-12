"""Tests for EasyIR hub discovery suggestion logic."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from custom_components.easyir.const import SUBENTRY_TYPE_HUB
from custom_components.easyir.discovery import _async_discover_hubs


class TestDiscovery(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_suggests_only_once_until_hub_state_changes(self) -> None:
        async_init = AsyncMock()
        hass = SimpleNamespace(
            data={},
            config_entries=SimpleNamespace(subentries=SimpleNamespace(async_init=async_init)),
        )
        parent = SimpleNamespace(entry_id="parent_entry")
        ts1201 = SimpleNamespace(
            id="device-1",
            identifiers={("zha", "aa:bb:cc:dd")},
            connections=set(),
        )

        with patch(
            "custom_components.easyir.discovery.parent_entry", return_value=parent
        ), patch(
            "custom_components.easyir.discovery.iter_zha_ts1201_devices",
            return_value=[ts1201],
        ), patch(
            "custom_components.easyir.discovery.configured_hub_ieees",
            return_value=set(),
        ):
            await _async_discover_hubs(hass)
            await _async_discover_hubs(hass)

        self.assertEqual(async_init.await_count, 1)
        args = async_init.await_args_list[0].args
        self.assertEqual(args[0], ("parent_entry", SUBENTRY_TYPE_HUB))

        with patch(
            "custom_components.easyir.discovery.parent_entry", return_value=parent
        ), patch(
            "custom_components.easyir.discovery.iter_zha_ts1201_devices",
            return_value=[ts1201],
        ), patch(
            "custom_components.easyir.discovery.configured_hub_ieees",
            return_value={"aa:bb:cc:dd"},
        ):
            await _async_discover_hubs(hass)

        with patch(
            "custom_components.easyir.discovery.parent_entry", return_value=parent
        ), patch(
            "custom_components.easyir.discovery.iter_zha_ts1201_devices",
            return_value=[ts1201],
        ), patch(
            "custom_components.easyir.discovery.configured_hub_ieees",
            return_value=set(),
        ):
            await _async_discover_hubs(hass)

        self.assertEqual(async_init.await_count, 2)


if __name__ == "__main__":
    unittest.main()

