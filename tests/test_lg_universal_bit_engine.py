"""Universal LG bit engine, strict decode, and send-path adapter tests."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "easyir"))

from protocols.lg_universal.engine import (
    LG_OFF_COMMAND,
    LgDecodeResult,
    decode_lg_ac_strict,
    encode_lg_ac_frame_universal,
    lg_ac_raw_timings_from_code,
    load_lg_universal_descriptor,
    profile_uses_lg_universal_encoder,
    valid_checksum,
)

HELPERS_PATH = ROOT / "custom_components" / "easyir" / "helpers.py"
_SPEC = importlib.util.spec_from_file_location("easyir_helpers", HELPERS_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
sys.modules["easyir_helpers"] = _HELPERS
_SPEC.loader.exec_module(_HELPERS)

resolve_profile_raw = _HELPERS.resolve_profile_raw
clear_profile_cache = _HELPERS.clear_profile_cache


class TestLgUniversalEngine(unittest.TestCase):
    def test_descriptor_has_references(self) -> None:
        d = load_lg_universal_descriptor()
        self.assertEqual(d.get("protocol_id"), "lg_universal_v1")
        refs = d.get("references") or []
        self.assertTrue(
            any("Arduino-IRremote" in str(r) for r in refs),
            "descriptor should cite Arduino-IRremote LG headers",
        )

    def test_profile_metadata_gate(self) -> None:
        on = profile_uses_lg_universal_encoder(
            {"easyir_protocol": "lg_universal_v1", "easyir_encoding": "lg28"}
        )
        self.assertTrue(on)
        self.assertFalse(
            profile_uses_lg_universal_encoder(
                {"easyir_protocol": "lg_universal_v1", "easyir_encoding": "raw"}
            )
        )
        self.assertFalse(profile_uses_lg_universal_encoder({}))

    def test_encode_off_and_raw_length(self) -> None:
        code = encode_lg_ac_frame_universal(
            power_on=False,
            hvac_mode="off",
            temperature_c=24,
            fan_mode="auto",
        )
        self.assertEqual(code, LG_OFF_COMMAND)
        raw = lg_ac_raw_timings_from_code(code)
        self.assertEqual(len(raw), 59)
        self.assertGreater(raw[0], 8000)

    def test_strict_decode_off(self) -> None:
        r = decode_lg_ac_strict(LG_OFF_COMMAND, supported_flags=frozenset({"power_off"}))
        self.assertIsInstance(r, LgDecodeResult)
        self.assertTrue(r.ok)
        self.assertTrue(r.is_off_command)
        self.assertTrue(r.signature_ok)

    def test_strict_decode_rejects_bad_checksum(self) -> None:
        good = encode_lg_ac_frame_universal(
            power_on=True,
            hvac_mode="cool",
            temperature_c=22,
            fan_mode="low",
        )
        bad = (good & 0xFFFFFFF0) | ((good + 1) & 0xF)
        self.assertFalse(valid_checksum(bad))
        r = decode_lg_ac_strict(bad)
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "checksum_mismatch")

    def test_strict_decode_rejects_wrong_signature(self) -> None:
        r = decode_lg_ac_strict(0x99ABCDEF, supported_flags=frozenset({"mode_temp_fan"}))
        self.assertFalse(r.ok)
        self.assertEqual(r.error, "invalid_signature")

    def test_roundtrip_state(self) -> None:
        code = encode_lg_ac_frame_universal(
            power_on=True,
            hvac_mode="cool",
            temperature_c=26,
            fan_mode="high",
        )
        r = decode_lg_ac_strict(code, supported_flags=frozenset({"mode_temp_fan"}))
        self.assertTrue(r.ok)
        self.assertTrue(r.power_on)
        self.assertEqual(r.hvac_mode, "cool")
        self.assertEqual(r.temperature_c, 26.0)
        self.assertEqual(r.fan_mode, "high")


class TestResolveProfileAdapter(unittest.TestCase):
    def setUp(self) -> None:
        clear_profile_cache()

    def tearDown(self) -> None:
        clear_profile_cache()

    def test_universal_profile_uses_synthesized_timings(self) -> None:
        payload = {
            "manufacturer": "LG",
            "operationModes": ["cool"],
            "fanModes": ["auto"],
            "minTemperature": 18,
            "maxTemperature": 30,
            "easyir_protocol": "lg_universal_v1",
            "easyir_encoding": "lg28",
            "commands": {"off": "[1,-2,3]", "cool": {"auto": {"24": "[9,-9,9]"}}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lg.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            off = resolve_profile_raw(path=str(path), action="off")
            self.assertEqual(len(off), 59)
            cool = resolve_profile_raw(
                path=str(path),
                action="cool",
                hvac_mode="cool",
                fan_mode="auto",
                temperature=24,
            )
            self.assertEqual(len(cool), 59)
            self.assertNotEqual(off, cool)

    def test_legacy_fallback_when_encoding_not_lg28(self) -> None:
        payload = {
            "easyir_protocol": "lg_universal_v1",
            "easyir_encoding": "raw",
            "commands": {
                "off": "[1000,-2000]",
                "cool": {"auto": {"24": "[3,-4,5]"}},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(
                resolve_profile_raw(path=str(path), action="off"),
                [1000, -2000],
            )
            self.assertEqual(
                resolve_profile_raw(
                    path=str(path),
                    action="cool",
                    hvac_mode="cool",
                    fan_mode="auto",
                    temperature=24,
                ),
                [3, -4, 5],
            )

    def test_universal_rejects_unsupported_hvac_in_metadata(self) -> None:
        payload = {
            "operationModes": ["cool"],
            "fanModes": ["auto"],
            "easyir_protocol": "lg_universal_v1",
            "easyir_encoding": "lg28",
            "commands": {"cool": {"auto": {"24": "[1]"}}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not supported"):
                resolve_profile_raw(
                    path=str(path),
                    action="cool",
                    hvac_mode="dry",
                    fan_mode="auto",
                    temperature=24,
                )


if __name__ == "__main__":
    unittest.main()
