"""Tests for remote button profile specs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from custom_components.easyir.remote_buttons import list_remote_button_specs


class TestRemoteButtonSpecs(unittest.TestCase):
    def test_demo_profile_yields_off_and_mode_buttons(self) -> None:
        repo = Path(__file__).resolve().parent.parent
        profile = repo / "custom_components" / "easyir" / "profiles" / "demo_ac.json"
        specs = list_remote_button_specs(str(profile))
        keys = {s.key for s in specs}
        self.assertIn("off", keys)
        self.assertTrue(any(k.startswith("cool_") for k in keys))

    def test_minimal_profile_off_only(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"commands": {"off": "[1,-2]"}}, handle)
            path = handle.name
        specs = list_remote_button_specs(path)
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].action, "off")


if __name__ == "__main__":
    unittest.main()
