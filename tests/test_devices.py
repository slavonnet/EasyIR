"""Device registry helper tests."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from custom_components.easyir.devices import _apply_device_area, _device_create_kwargs


class TestDevices(unittest.TestCase):
    def test_device_create_kwargs_skips_unknown_subentry_param(self) -> None:
        reg = MagicMock()
        reg.async_get_or_create = MagicMock()

        kwargs = _device_create_kwargs(
            reg,
            {
                "config_entry_id": "parent",
                "config_subentry_id": "hub-1",
                "identifiers": {("easyir", "hub_hub-1")},
            },
        )
        self.assertNotIn("config_subentry_id", kwargs)
        self.assertEqual(kwargs["config_entry_id"], "parent")

    def test_apply_device_area_updates_when_needed(self) -> None:
        reg = MagicMock()
        device = MagicMock()
        device.id = "dev-1"
        device.area_id = None
        _apply_device_area(reg, device, "living_room")
        reg.async_update_device.assert_called_once_with("dev-1", area_id="living_room")

    def test_apply_device_area_skips_when_unchanged(self) -> None:
        reg = MagicMock()
        device = MagicMock()
        device.id = "dev-1"
        device.area_id = "living_room"
        _apply_device_area(reg, device, "living_room")
        reg.async_update_device.assert_not_called()


if __name__ == "__main__":
    unittest.main()
