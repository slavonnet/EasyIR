"""Tests for remote button profile specs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from custom_components.easyir.remote_buttons import (
    ButtonCommandKind,
    list_remote_button_specs,
)

ROOT = Path(__file__).resolve().parent.parent
PROFILE_7062 = ROOT / "custom_components" / "easyir" / "profiles" / "climate" / "7062.json"


class TestRemoteButtonSpecs(unittest.TestCase):
    def test_demo_profile_yields_off_and_mode_buttons(self) -> None:
        profile = ROOT / "custom_components" / "easyir" / "profiles" / "demo_ac.json"
        specs = list_remote_button_specs(str(profile))
        keys = {s.key for s in specs}
        self.assertIn("off", keys)
        self.assertTrue(any(k.startswith("cool_") for k in keys))
        cool = next(s for s in specs if s.key.startswith("cool_"))
        self.assertEqual(cool.kind, ButtonCommandKind.STATE_FRAME)
        self.assertIsNotNone(cool.fan_mode)

    def test_lg_universal_profile_has_feature_buttons_not_mode_matrix(self) -> None:
        specs = list_remote_button_specs(str(PROFILE_7062))
        keys = {s.key for s in specs}
        self.assertIn("off", keys)
        self.assertIn("ionizer_on", keys)
        self.assertIn("ionizer_off", keys)
        self.assertIn("energy_saving_on", keys)
        self.assertIn("auto_clean_on", keys)
        self.assertIn("jet_on", keys)
        self.assertIn("swing_on", keys)
        self.assertIn("wall_swing_on", keys)
        self.assertIn("light", keys)
        self.assertIn("power_down", keys)
        self.assertIn("clear_timers", keys)
        self.assertFalse(any(k.startswith("cool_") for k in keys))

        ion_on = next(s for s in specs if s.key == "ionizer_on")
        self.assertEqual(ion_on.kind, ButtonCommandKind.FEATURE_COMMAND)
        self.assertEqual(ion_on.action, "ionizer_on")
        self.assertIsNone(ion_on.hvac_mode)
        self.assertIsNone(ion_on.fan_mode)
        self.assertIsNone(ion_on.temperature)

        off_btn = next(s for s in specs if s.key == "off")
        self.assertEqual(off_btn.kind, ButtonCommandKind.STATE_FRAME)
        self.assertEqual(off_btn.label, "Power toggle")

    def test_minimal_profile_off_only(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"commands": {"off": "[1,-2]"}}, handle)
            path = handle.name
        specs = list_remote_button_specs(path)
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].action, "off")
        self.assertEqual(specs[0].kind, ButtonCommandKind.STATE_FRAME)


if __name__ == "__main__":
    unittest.main()
