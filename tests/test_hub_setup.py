"""Tests for hub setup helpers (endpoint resolution)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from custom_components.easyir.endpoint import endpoint_for_ieee, endpoint_for_zha_device


class TestEndpointResolution(unittest.TestCase):
    def test_default_endpoint_for_zha_device(self) -> None:
        self.assertEqual(endpoint_for_zha_device(None), 1)

    def test_endpoint_from_ieee_without_device_registry(self) -> None:
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
