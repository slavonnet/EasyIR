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
encode_raw_to_tuya_base64 = _HELPERS_MODULE.encode_raw_to_tuya_base64
resolve_profile_raw = _HELPERS_MODULE.resolve_profile_raw


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


if __name__ == "__main__":
    unittest.main()
