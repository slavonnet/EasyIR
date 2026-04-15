"""Tests for supported hub discovery helpers (no Home Assistant runtime)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from custom_components.easyir.supported_hubs import list_onboarding_hub_choices  # noqa: E402


class TestOnboardingHubChoices(unittest.TestCase):
    def test_lists_unconfigured_ts1201_only(self) -> None:
        dev = MagicMock()
        dev.disabled_by = None
        dev.identifiers = {("zha", "aa:bb:cc:dd:ee:ff")}
        dev.connections = set()
        dev.model = "TS1201"
        dev.model_id = None
        dev.name = "IR Blaster"
        dev.name_by_user = None
        dev.id = "reg_dev_1"

        other = MagicMock()
        other.disabled_by = None
        other.identifiers = {("zha", "11:22:33:44:55:66")}
        other.connections = set()
        other.model = "TH02"
        other.model_id = None
        other.id = "reg_dev_2"

        reg = MagicMock()
        reg.devices = {"reg_dev_1": dev, "reg_dev_2": other}

        hass = MagicMock()
        hass.config_entries.async_entries.return_value = []

        with patch(
            "custom_components.easyir.supported_hubs.dr.async_get",
            return_value=reg,
        ):
            choices = list_onboarding_hub_choices(hass)

        self.assertEqual(choices, [("reg_dev_1", "IR Blaster (aa:bb:cc:dd:ee:ff)")])

    def test_excludes_already_configured_ieee(self) -> None:
        dev = MagicMock()
        dev.disabled_by = None
        dev.identifiers = {("zha", "aa:bb:cc")}
        dev.connections = set()
        dev.model = "TS1201"
        dev.model_id = None
        dev.name = "Hub"
        dev.name_by_user = None
        dev.id = "d1"

        reg = MagicMock()
        reg.devices = {"d1": dev}

        entry = MagicMock()
        entry.data = {"ieee": "AA:BB:CC"}

        hass = MagicMock()
        hass.config_entries.async_entries.return_value = [entry]

        with patch(
            "custom_components.easyir.supported_hubs.dr.async_get",
            return_value=reg,
        ):
            choices = list_onboarding_hub_choices(hass)

        self.assertEqual(choices, [])
