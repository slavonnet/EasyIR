"""Tests for LG P12RK pilot protocol encode/decode and capability binding."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Import `protocols.*` from the integration package without loading `easyir` HA entry.
sys.path.insert(0, str(ROOT / "custom_components" / "easyir"))

from protocols.lg_p12rk.bind import climate_capability_view, is_lg_p12rk_profile
from protocols.lg_p12rk.engine import (
    LG_OFF_COMMAND,
    decode_lg_ac_frame,
    encode_lg_ac_frame,
    load_lg_p12rk_capabilities,
    load_lg_p12rk_descriptor,
    valid_checksum,
)


class TestLgAcFrame(unittest.TestCase):
    def test_off_command_decode(self) -> None:
        st = decode_lg_ac_frame(LG_OFF_COMMAND)
        self.assertFalse(st.power_on)
        self.assertTrue(st.is_off_command)
        self.assertEqual(st.hvac_mode, "off")

    def test_encode_decode_roundtrip_cool(self) -> None:
        code = encode_lg_ac_frame(
            power_on=True,
            hvac_mode="cool",
            temperature_c=24,
            fan_mode="auto",
        )
        self.assertTrue(valid_checksum(code))
        st = decode_lg_ac_frame(code)
        self.assertTrue(st.power_on)
        self.assertEqual(st.hvac_mode, "cool")
        self.assertEqual(st.temperature_c, 24)
        self.assertEqual(st.fan_mode, "auto")

    def test_roundtrip_dry_mid(self) -> None:
        code = encode_lg_ac_frame(
            power_on=True,
            hvac_mode="dry",
            temperature_c=22,
            fan_mode="mid",
        )
        st = decode_lg_ac_frame(code)
        self.assertEqual(st.hvac_mode, "dry")
        self.assertEqual(st.temperature_c, 22)
        self.assertEqual(st.fan_mode, "mid")

    def test_fan_medium_alias(self) -> None:
        code = encode_lg_ac_frame(
            power_on=True,
            hvac_mode="cool",
            temperature_c=20,
            fan_mode="medium",
        )
        st = decode_lg_ac_frame(code)
        self.assertEqual(st.fan_mode, "mid")

    def test_descriptor_loads(self) -> None:
        d = load_lg_p12rk_descriptor()
        self.assertEqual(d.get("schema_version"), 1)
        self.assertIn("P12RK", d.get("pilot_models", []))

    def test_capabilities_ionizer_flag(self) -> None:
        c = load_lg_p12rk_capabilities()
        ion = (c.get("optional_features") or {}).get("ionizer") or {}
        self.assertIn("supported", ion)
        self.assertFalse(ion.get("supported"))


class TestCapabilityBinding(unittest.TestCase):
    def test_detects_lg_p12rk_profile(self) -> None:
        payload = {
            "manufacturer": "LG",
            "supportedModels": ["P12RK"],
            "commands": {"off": "[1,-2,3]"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertTrue(is_lg_p12rk_profile(str(path)))
            view = climate_capability_view(str(path))
            self.assertTrue(view["pilot"])
            self.assertEqual(view["protocol"], "lg_p12rk")
            self.assertIn("cool", view["hvac_modes"])
            self.assertFalse(view["ionizer_supported"])

    def test_non_pilot_profile(self) -> None:
        payload = {"manufacturer": "Other", "supportedModels": ["X"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertFalse(is_lg_p12rk_profile(str(path)))
            view = climate_capability_view(str(path))
            self.assertFalse(view.get("pilot"))


if __name__ == "__main__":
    unittest.main()
