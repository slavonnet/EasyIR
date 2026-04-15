"""Tests for canonical IR model, codec registry, and service adapter (no Home Assistant)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CUSTOM = REPO_ROOT / "custom_components"
HELPERS_PATH = CUSTOM / "easyir" / "helpers.py"

_SPEC = importlib.util.spec_from_file_location("easyir_helpers", HELPERS_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load helpers module for tests")
_HELPERS = importlib.util.module_from_spec(_SPEC)
sys.modules["easyir_helpers"] = _HELPERS
_SPEC.loader.exec_module(_HELPERS)

clear_profile_cache = _HELPERS.clear_profile_cache
decode_broadlink_base64_to_raw = _HELPERS.decode_broadlink_base64_to_raw
decode_tuya_learn_base64_to_raw = _HELPERS.decode_tuya_learn_base64_to_raw
encode_raw_to_broadlink_base64 = _HELPERS.encode_raw_to_broadlink_base64
encode_raw_to_tuya_learn_base64 = _HELPERS.encode_raw_to_tuya_learn_base64
encode_raw_to_tuya_base64 = _HELPERS.encode_raw_to_tuya_base64
resolve_profile_raw = _HELPERS.resolve_profile_raw

if str(CUSTOM) not in sys.path:
    sys.path.insert(0, str(CUSTOM))

from easyir.ir_core.codec_raw_timings import RawTimingsCodec
from easyir.ir_core.registry import default_codec_registry
from easyir.ir_core.service_adapter import (
    encode_profile_command_for_zha_ts1201,
    encode_raw_timings_for_zha_ts1201,
)


class TestCanonicalModelAndCodec(unittest.TestCase):
    def test_raw_timings_codec_roundtrip(self) -> None:
        codec = RawTimingsCodec()
        timings = [1000, -2000, 500]
        frame = codec.frame_from_timings(timings, protocol_hint="test")
        self.assertEqual(frame.timings, timings)
        self.assertEqual(codec.timings_from_frame(frame), timings)
        self.assertEqual(frame.protocol_hint, "test")

    def test_default_registry_matches_legacy_encode(self) -> None:
        reg = default_codec_registry()
        codec = reg.get_codec("raw_timings")
        timings = [1, -2, 300]
        frame = codec.frame_from_timings(timings)
        code = reg.encode_for_transport("ts1201_zha", frame)
        self.assertEqual(code, encode_raw_to_tuya_base64(timings))

    def test_default_registry_encodes_broadlink_transport(self) -> None:
        reg = default_codec_registry()
        codec = reg.get_codec("raw_timings")
        timings = [8900, -4150, 500, -550, 500, -1580]
        frame = codec.frame_from_timings(timings)
        payload = reg.encode_for_transport("broadlink_base64", frame)
        self.assertEqual(payload, encode_raw_to_broadlink_base64(timings))
        decoded = decode_broadlink_base64_to_raw(payload)
        self.assertEqual(len(decoded), len(timings))
        for got, exp in zip(decoded, timings):
            self.assertLessEqual(abs(got - exp), 80)

    def test_default_registry_encodes_tuya_learn_transport(self) -> None:
        reg = default_codec_registry()
        codec = reg.get_codec("raw_timings")
        timings = [8956, -4138, 520, -1576, 520, -520, 520, -1576, 520]
        frame = codec.frame_from_timings(timings)
        payload = reg.encode_for_transport("tuya_learn_base64", frame)
        self.assertEqual(payload, encode_raw_to_tuya_learn_base64(timings))
        decoded = decode_tuya_learn_base64_to_raw(payload)
        self.assertEqual(decoded, timings)


class TestServiceAdapter(unittest.TestCase):
    def setUp(self) -> None:
        clear_profile_cache()

    def tearDown(self) -> None:
        clear_profile_cache()

    def test_send_raw_path_matches_legacy(self) -> None:
        timings = [1, -2, 300]
        frame, code = encode_raw_timings_for_zha_ts1201(timings)
        self.assertEqual(frame.timings, timings)
        self.assertEqual(code, encode_raw_to_tuya_base64(timings))

    def test_send_profile_path_matches_legacy(self) -> None:
        payload = {"commands": {"off": "[1000,-2000,500]"}}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            p = str(path)
            frame, code = encode_profile_command_for_zha_ts1201(
                profile_path=p,
                action="off",
                hvac_mode=None,
                fan_mode=None,
                temperature=None,
            )
            raw = resolve_profile_raw(path=p, action="off")
            self.assertEqual(frame.timings, raw)
            self.assertEqual(code, encode_raw_to_tuya_base64(raw))


if __name__ == "__main__":
    unittest.main()
