"""Audit test: LG profiles -> TS1201 base64 -> universal LG decode.

Goal of this audit:
- run over all bundled LG climate profiles,
- parse profile raw commands,
- encode to TS1201 base64 and decode back to raw timings,
- try to parse first LG28 frame and decode with universal decoder,
- classify outcomes:
  1) exact HVAC match,
  2) HVAC match but with extra bits (non-canonical frame),
  3) decoded HVAC mismatch vs profile key tuple,
  4) non-LG/other protocol frame,
  5) non-HVAC LG command/flag frame,
  6) invalid/unsupported profile payload.

This audit intentionally does not require full parity for every legacy LG file.
It provides a deterministic signal about where universal support is complete and
where protocol variants/extra bits remain.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "easyir"))

from protocols.lg_universal.engine import decode_lg_ac_strict, encode_lg_ac_frame_universal

HELPERS_PATH = ROOT / "custom_components" / "easyir" / "helpers.py"
_SPEC = importlib.util.spec_from_file_location("easyir_helpers", HELPERS_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
sys.modules["easyir_helpers"] = _HELPERS
_SPEC.loader.exec_module(_HELPERS)

encode_raw_to_tuya_base64 = _HELPERS.encode_raw_to_tuya_base64

CLIMATE_DIR = ROOT / "custom_components" / "easyir" / "profiles" / "climate"


@dataclass
class AuditSummary:
    total_cases: int = 0
    exact_match: int = 0
    match_with_extra_bits: int = 0
    state_mismatch: int = 0
    non_lg_or_other_protocol: int = 0
    non_hvac_flag_frame: int = 0
    invalid_profile_payload: int = 0
    samples: dict[str, list[str]] = field(
        default_factory=lambda: {
            "exact_match": [],
            "match_with_extra_bits": [],
            "state_mismatch": [],
            "non_lg_or_other_protocol": [],
            "non_hvac_flag_frame": [],
            "invalid_profile_payload": [],
        }
    )

    def add(self, category: str, sample: str | None = None) -> None:
        setattr(self, category, getattr(self, category) + 1)
        if sample and len(self.samples[category]) < 10:
            self.samples[category].append(sample)

    def classified_total(self) -> int:
        return (
            self.exact_match
            + self.match_with_extra_bits
            + self.state_mismatch
            + self.non_lg_or_other_protocol
            + self.non_hvac_flag_frame
            + self.invalid_profile_payload
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "exact_match": self.exact_match,
            "match_with_extra_bits": self.match_with_extra_bits,
            "state_mismatch": self.state_mismatch,
            "non_lg_or_other_protocol": self.non_lg_or_other_protocol,
            "non_hvac_flag_frame": self.non_hvac_flag_frame,
            "invalid_profile_payload": self.invalid_profile_payload,
            "samples": self.samples,
        }


def _parse_profile_raw(raw: Any) -> list[int]:
    if isinstance(raw, (list, tuple)):
        return [int(x) for x in raw]
    if not isinstance(raw, str):
        raise ValueError(f"Unsupported raw payload type: {type(raw).__name__}")
    value = json.loads(raw)
    if not isinstance(value, list):
        raise ValueError("Profile raw payload must decode to list")
    return [int(x) for x in value]


def _decode_tuya_base64_to_raw(payload: str) -> list[int]:
    """Invert TS1201 chunked base64 payload to alternating mark/space timings."""
    data = base64.b64decode(payload.encode())
    pos = 0
    bytes_flat: list[int] = []
    while pos < len(data):
        chunk_len = data[pos] + 1
        pos += 1
        chunk = data[pos : pos + chunk_len]
        pos += chunk_len
        bytes_flat.extend(chunk)

    u16: list[int] = []
    for i in range(0, len(bytes_flat), 2):
        if i + 1 >= len(bytes_flat):
            break
        v = bytes_flat[i] | (bytes_flat[i + 1] << 8)
        u16.append(v)

    timings: list[int] = []
    for i, val in enumerate(u16):
        timings.append(val if i % 2 == 0 else -val)
    return timings


def _extract_first_lg28_code(raw: list[int]) -> int | None:
    """Try to recover first valid LG28 frame from raw timings."""
    # Accept both classic LG AC (8.8/4.2 ms) and LG2-like (3.2/9.9 ms) headers.
    # Then read 28 mark/space pairs and validate with strict decoder.
    for i in range(0, max(0, len(raw) - 58)):
        hm = raw[i]
        hs = raw[i + 1]
        if hm <= 0 or hs >= 0:
            continue
        ahm = abs(hm)
        ahs = abs(hs)
        header_ok = (8200 <= ahm <= 9500 and 3500 <= ahs <= 5000) or (
            2500 <= ahm <= 3800 and 9000 <= ahs <= 11000
        )
        if not header_ok:
            continue

        code = 0
        ok = True
        for bit_idx in range(28):
            mark = raw[i + 2 + bit_idx * 2]
            space = raw[i + 3 + bit_idx * 2]
            if mark <= 0 or space >= 0:
                ok = False
                break
            am = abs(mark)
            asp = abs(space)
            if not (320 <= am <= 700 and 350 <= asp <= 2000):
                ok = False
                break
            bit = 1 if asp >= 1000 else 0
            code = (code << 1) | bit

        if not ok:
            continue
        result = decode_lg_ac_strict(code)
        if result.signature_ok and result.checksum_valid:
            return code
    return None


def _normalize_mode(action: str) -> str:
    a = action.strip().lower()
    if a == "fan":
        return "fan_only"
    return a


def _normalize_fan(fan: str) -> str:
    return {"medium": "mid"}.get(fan.strip().lower(), fan.strip().lower())


class TestLgProfileMatrixRoundtrip(unittest.TestCase):
    def test_lg_profiles_roundtrip_matrix(self) -> None:
        lg_profiles: list[Path] = []
        for path in sorted(CLIMATE_DIR.glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if str(doc.get("manufacturer", "")).strip().upper() == "LG":
                lg_profiles.append(path)

        self.assertGreater(len(lg_profiles), 0, "No LG profiles found for audit")

        summary = AuditSummary()
        non_hvac_errors = {
            "command_word_not_hvac_state",
            "unknown_command_word",
            "unsupported_hvac_state",
        }

        for path in lg_profiles:
            doc = json.loads(path.read_text(encoding="utf-8"))
            commands = doc.get("commands") or {}
            if not isinstance(commands, dict):
                continue

            for action, fan_tree in commands.items():
                action_norm = _normalize_mode(str(action))
                if action_norm == "off":
                    continue
                if not isinstance(fan_tree, dict):
                    continue

                for fan_mode, temp_tree in fan_tree.items():
                    if not isinstance(temp_tree, dict):
                        continue
                    fan_norm = _normalize_fan(str(fan_mode))

                    for temp_key, raw_payload in temp_tree.items():
                        summary.total_cases += 1
                        try:
                            expected_temp = float(int(str(temp_key)))
                            raw = _parse_profile_raw(raw_payload)
                            b64 = encode_raw_to_tuya_base64(raw)
                            raw_roundtrip = _decode_tuya_base64_to_raw(b64)
                            code = _extract_first_lg28_code(raw_roundtrip)
                        except Exception as err:
                            summary.add(
                                "invalid_profile_payload",
                                f"{path.name}:{action_norm}:{fan_norm}:{temp_key}:{err}",
                            )
                            continue

                        if code is None:
                            summary.add(
                                "non_lg_or_other_protocol",
                                f"{path.name}:{action_norm}:{fan_norm}:{temp_key}:no_lg28",
                            )
                            continue

                        result = decode_lg_ac_strict(code)
                        if not result.ok:
                            category = (
                                "non_hvac_flag_frame"
                                if result.error in non_hvac_errors
                                else "non_lg_or_other_protocol"
                            )
                            summary.add(
                                category,
                                f"{path.name}:{action_norm}:{fan_norm}:{temp_key}:{result.error}",
                            )
                            continue

                        if not (
                            result.hvac_mode == action_norm
                            and result.fan_mode == fan_norm
                            and result.temperature_c == expected_temp
                        ):
                            summary.add(
                                "state_mismatch",
                                (
                                    f"{path.name}:{action_norm}:{fan_norm}:{expected_temp}"
                                    f"->decoded({result.hvac_mode},{result.fan_mode},{result.temperature_c})"
                                ),
                            )
                            continue

                        canonical = encode_lg_ac_frame_universal(
                            power_on=True,
                            hvac_mode=result.hvac_mode,
                            temperature_c=int(result.temperature_c or 24),
                            fan_mode=result.fan_mode,
                        )
                        if (canonical & 0x0FFFFFFF) == (code & 0x0FFFFFFF):
                            summary.add(
                                "exact_match",
                                f"{path.name}:{action_norm}:{fan_norm}:{temp_key}",
                            )
                        else:
                            summary.add(
                                "match_with_extra_bits",
                                (
                                    f"{path.name}:{action_norm}:{fan_norm}:{temp_key}"
                                    f":code={code:#x}:canonical={canonical:#x}"
                                ),
                            )

        self.assertGreater(summary.total_cases, 0, "No LG action/fan/temp cases found")
        self.assertEqual(
            summary.classified_total(),
            summary.total_cases,
            f"Audit classification lost cases: {json.dumps(summary.as_dict(), ensure_ascii=False)}",
        )
        self.assertGreater(
            summary.exact_match + summary.match_with_extra_bits,
            0,
            f"No LG HVAC states decoded by universal engine: {json.dumps(summary.as_dict(), ensure_ascii=False)}",
        )

        # Helpful audit output in verbose CI logs.
        print("LG_PROFILE_MATRIX_AUDIT", json.dumps(summary.as_dict(), ensure_ascii=False))

