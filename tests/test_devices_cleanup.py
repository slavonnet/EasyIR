"""Tests for cleanup of stale EasyIR hub/remote device links."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from custom_components.easyir.devices import (
    async_cleanup_removed_subentry_devices,
    hub_device_identifier,
    remote_device_identifier,
)


class _FakeRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def async_update_device(self, device_id: str, **kwargs) -> None:
        self.calls.append((device_id, kwargs))


class TestDevicesCleanup(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_removes_config_entry_for_orphan_easyir_device(self) -> None:
        reg = _FakeRegistry()
        hass = SimpleNamespace()
        entry = SimpleNamespace(entry_id="easyir_entry")
        orphan = SimpleNamespace(
            id="dev-1",
            identifiers={("easyir", "remote_old_1")},
        )

        with patch(
            "custom_components.easyir.devices.dr.async_get", return_value=reg
        ), patch(
            "custom_components.easyir.devices.dr.async_entries_for_config_entry",
            return_value=[orphan],
        ):
            await async_cleanup_removed_subentry_devices(
                hass,
                entry,
                hubs=[],
                remotes=[],
            )

        self.assertEqual(len(reg.calls), 1)
        self.assertEqual(reg.calls[0][0], "dev-1")
        self.assertEqual(
            reg.calls[0][1],
            {"remove_config_entry_id": "easyir_entry"},
        )

    async def test_cleanup_drops_only_stale_identifier_when_device_is_still_active(self) -> None:
        reg = _FakeRegistry()
        hass = SimpleNamespace()
        entry = SimpleNamespace(entry_id="easyir_entry")
        active_hub_ident = hub_device_identifier("hub_a")
        stale_remote_ident = remote_device_identifier("remote_old")
        mixed = SimpleNamespace(
            id="dev-2",
            identifiers={active_hub_ident, stale_remote_ident, ("zha", "zigbee-dev")},
        )
        hubs = [SimpleNamespace(subentry_id="hub_a")]

        with patch(
            "custom_components.easyir.devices.dr.async_get", return_value=reg
        ), patch(
            "custom_components.easyir.devices.dr.async_entries_for_config_entry",
            return_value=[mixed],
        ):
            await async_cleanup_removed_subentry_devices(
                hass,
                entry,
                hubs=hubs,
                remotes=[],
            )

        self.assertEqual(len(reg.calls), 1)
        self.assertEqual(reg.calls[0][0], "dev-2")
        kwargs = reg.calls[0][1]
        self.assertIn("new_identifiers", kwargs)
        self.assertEqual(
            kwargs["new_identifiers"],
            {active_hub_ident, ("zha", "zigbee-dev")},
        )


if __name__ == "__main__":
    unittest.main()

