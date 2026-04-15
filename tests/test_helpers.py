"""Unit tests for helper functions."""

from __future__ import annotations

import json
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HELPERS_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "easyir"
    / "helpers.py"
)
_SPEC = importlib.util.spec_from_file_location("easyir_helpers", HELPERS_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load helpers module for tests")
_HELPERS_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["easyir_helpers"] = _HELPERS_MODULE
_SPEC.loader.exec_module(_HELPERS_MODULE)

clear_profile_cache = _HELPERS_MODULE.clear_profile_cache
decode_ir_payload = _HELPERS_MODULE.decode_ir_payload
decode_ir_payload_auto = _HELPERS_MODULE.decode_ir_payload_auto
decode_tuya_base64_to_raw = _HELPERS_MODULE.decode_tuya_base64_to_raw
decode_broadlink_base64_to_raw = _HELPERS_MODULE.decode_broadlink_base64_to_raw
encode_raw_to_tuya_base64 = _HELPERS_MODULE.encode_raw_to_tuya_base64
encode_raw_to_broadlink_base64 = _HELPERS_MODULE.encode_raw_to_broadlink_base64
resolve_profile_raw = _HELPERS_MODULE.resolve_profile_raw
transcode_ir_payload = _HELPERS_MODULE.transcode_ir_payload


class TestEncodeRawToTuyaBase64(unittest.TestCase):
    def test_encodes_small_sequence(self) -> None:
        self.assertEqual(
            encode_raw_to_tuya_base64([1, -2, 300]),
            "BQEAAgAsAQ==",
        )

    def test_caps_values_to_uint16(self) -> None:
        self.assertEqual(
            encode_raw_to_tuya_base64([70000]),
            "Af//",
        )


class TestResolveProfileRaw(unittest.TestCase):
    def setUp(self) -> None:
        clear_profile_cache()

    def tearDown(self) -> None:
        clear_profile_cache()

    def test_resolves_off_action(self) -> None:
        payload = {"commands": {"off": "[1000,-2000,500]"}}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = resolve_profile_raw(path=str(path), action="off")

        self.assertEqual(result, [1000, -2000, 500])

    def test_requires_mode_params_for_non_off(self) -> None:
        payload = {
            "commands": {
                "cool": {
                    "auto": {
                        "24": "[111,-222,333]",
                    }
                }
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "provide hvac_mode, fan_mode and temperature"
            ):
                resolve_profile_raw(path=str(path), action="cool")

    def test_resolves_json_array_not_string(self) -> None:
        payload = {
            "commands": {
                "cool": {
                    "auto": {
                        "24": [3198, -9806, 487, -1553],
                    }
                }
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = resolve_profile_raw(
                path=str(path),
                action="cool",
                hvac_mode="cool",
                fan_mode="auto",
                temperature=24,
            )
        self.assertEqual(result, [3198, -9806, 487, -1553])

    def test_rejects_empty_raw_string(self) -> None:
        payload = {"commands": {"off": ""}}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "empty"):
                resolve_profile_raw(path=str(path), action="off")

    def test_resolves_nested_command_tree(self) -> None:
        payload = {
            "commands": {
                "cool": {
                    "auto": {
                        "24": "[3198,-9806,487,-1553]",
                    }
                }
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = resolve_profile_raw(
                path=str(path),
                action="cool",
                hvac_mode="cool",
                fan_mode="auto",
                temperature=24,
            )

        self.assertEqual(result, [3198, -9806, 487, -1553])

    def test_resolves_fan_mode_medium_alias(self) -> None:
        payload = {
            "commands": {
                "cool": {
                    "mid": {
                        "24": "[1,-2,3,4]",
                    }
                }
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = resolve_profile_raw(
                path=str(path),
                action="cool",
                hvac_mode="cool",
                fan_mode="medium",
                temperature=24,
            )
        self.assertEqual(result, [1, -2, 3, 4])

    def test_uses_cache_when_file_unchanged(self) -> None:
        payload = {"commands": {"off": "[1,-2,3]"}}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            first = resolve_profile_raw(path=str(path), action="off")
            # Corrupt read_text result while keeping stat mtime unchanged.
            fixed_mtime = path.stat().st_mtime_ns
            with patch(
                "easyir_helpers.Path.stat",
                return_value=type("Stat", (), {"st_mtime_ns": fixed_mtime})(),
            ), patch(
                "easyir_helpers.Path.read_text",
                return_value="{",
            ):
                second = resolve_profile_raw(path=str(path), action="off")

        self.assertEqual(first, [1, -2, 3])
        self.assertEqual(second, [1, -2, 3])

    def test_invalidates_cache_after_file_change(self) -> None:
        payload_v1 = {"commands": {"off": "[10,-20,30]"}}
        payload_v2 = {"commands": {"off": "[40,-50,60]"}}

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps(payload_v1), encoding="utf-8")
            first = resolve_profile_raw(path=str(path), action="off")

            path.write_text(json.dumps(payload_v2), encoding="utf-8")
            current_mtime = path.stat().st_mtime_ns
            os.utime(path, ns=(current_mtime + 1_000_000_000, current_mtime + 1_000_000_000))
            time.sleep(0.01)
            second = resolve_profile_raw(path=str(path), action="off")

        self.assertEqual(first, [10, -20, 30])
        self.assertEqual(second, [40, -50, 60])


class TestIrPayloadDecodeAndTranscode(unittest.TestCase):
    def test_decode_tuya_roundtrip(self) -> None:
        raw = [9000, -4500, 560, -560, 560, -1690]
        payload = encode_raw_to_tuya_base64(raw)
        decoded = decode_ir_payload(payload, encoding="tuya")
        self.assertEqual(decoded.source_encoding, "tuya_base64")
        self.assertEqual(decoded.raw_timings, raw)
        self.assertEqual(decode_tuya_base64_to_raw(payload), raw)

    def test_decode_broadlink_roundtrip(self) -> None:
        raw = [9024, -4512, 564, -564, 564, -1688]
        payload = encode_raw_to_broadlink_base64(raw)
        decoded = decode_ir_payload(payload, encoding="base64")
        self.assertEqual(decoded.source_encoding, "broadlink_base64")
        recovered = decoded.raw_timings
        self.assertEqual(len(recovered), len(raw))
        for got, exp in zip(recovered, raw):
            # Broadlink is unit-quantized, microseconds are approximate.
            self.assertLessEqual(abs(got - exp), 80)
        self.assertEqual(recovered, decode_broadlink_base64_to_raw(payload))

    def test_decode_auto_detects_raw_json(self) -> None:
        payload = "[1000, -2000, 500]"
        decoded = decode_ir_payload_auto(payload)
        self.assertEqual(decoded.source_encoding, "raw")
        self.assertEqual(decoded.raw_timings, [1000, -2000, 500])

    def test_decode_auto_detects_tuya_base64(self) -> None:
        raw = [1000, -2000, 500, -600]
        payload = encode_raw_to_tuya_base64(raw)
        decoded = decode_ir_payload_auto(payload)
        self.assertEqual(decoded.source_encoding, "tuya_base64")
        self.assertEqual(decoded.raw_timings, raw)

    def test_decode_auto_detects_broadlink_base64(self) -> None:
        raw = [8890, -4175, 500, -550, 500, -1580]
        payload = encode_raw_to_broadlink_base64(raw)
        decoded = decode_ir_payload_auto(payload)
        self.assertEqual(decoded.source_encoding, "broadlink_base64")
        self.assertEqual(len(decoded.raw_timings), len(raw))

    def test_transcode_between_vendor_formats_via_raw(self) -> None:
        raw = [8900, -4150, 500, -550, 500, -1580]
        broadlink_payload = transcode_ir_payload(raw, target_encoding="broadlink")
        self.assertIsInstance(broadlink_payload, str)
        tuya_payload = transcode_ir_payload(
            broadlink_payload,
            source_encoding="auto",
            target_encoding="tuya",
        )
        self.assertIsInstance(tuya_payload, str)
        decoded = decode_tuya_base64_to_raw(str(tuya_payload))
        self.assertEqual(len(decoded), len(raw))

    def test_resolve_profile_raw_supports_base64_commands_encoding(self) -> None:
        raw = [8890, -4175, 500, -550, 500, -1580]
        payload = {
            "commandsEncoding": "Base64",
            "commands": {"off": encode_raw_to_broadlink_base64(raw)},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            resolved = resolve_profile_raw(path=str(path), action="off")
        self.assertEqual(len(resolved), len(raw))
        for got, exp in zip(resolved, raw):
            self.assertLessEqual(abs(got - exp), 80)

    def test_resolve_profile_raw_falls_back_to_auto_when_hint_invalid(self) -> None:
        payload = {
            "commandsEncoding": "Tuya",  # wrong hint for this JSON raw payload
            "commands": {"off": "[1, -2, 3, -4]"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            resolved = resolve_profile_raw(path=str(path), action="off")
        self.assertEqual(resolved, [1, -2, 3, -4])


if __name__ == "__main__":
    unittest.main()
