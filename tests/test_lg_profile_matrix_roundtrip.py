"""Audit test: all LG profiles with auto-detected command encoding.

Pipeline per case:
  profile payload (unknown vendor format)
    -> decode_ir_payload_auto (canonical raw timings)
    -> encode_raw_to_tuya_base64 (transport transcoding check)
    -> decode_tuya_base64_to_raw (canonical raw timings again)
    -> extract/decode LG28 state
    -> classify + rank mismatches/extra bits.

The test validates the "any format -> canonical -> any format" direction and
prints ranked diagnostics for protocol coverage planning.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from collections import Counter
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
decode_ir_payload_auto = _HELPERS.decode_ir_payload_auto
decode_tuya_base64_to_raw = _HELPERS.decode_tuya_base64_to_raw

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
    detected_encodings: Counter[str] = field(default_factory=Counter)
    declared_encodings: Counter[str] = field(default_factory=Counter)
    state_mismatch_by_model: Counter[str] = field(default_factory=Counter)
    state_mismatch_by_mode: Counter[str] = field(default_factory=Counter)
    state_mismatch_by_profile: Counter[str] = field(default_factory=Counter)
    extra_bits_by_command_pair: Counter[str] = field(default_factory=Counter)
    extra_bits_by_diff_mask: Counter[str] = field(default_factory=Counter)
    extra_bits_by_position: Counter[int] = field(default_factory=Counter)
    extra_bits_domain: Counter[str] = field(default_factory=Counter)
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

    @staticmethod
    def _top(counter: Counter[Any], limit: int = 10) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, count in counter.most_common(limit):
            rows.append({"key": key, "count": count})
        return rows

    @staticmethod
    def _bit_domain(bit: int) -> str:
        if 4 <= bit <= 7:
            return "fan_bits"
        if 8 <= bit <= 11:
            return "temperature_bits"
        if 12 <= bit <= 14:
            return "mode_bits"
        if 15 <= bit <= 19:
            return "command_word_high_bits"
        if 20 <= bit <= 27:
            return "signature_or_control_bits"
        return "checksum_or_low_control_bits"

    def as_dict(self) -> dict[str, Any]:
        ranked_bits: list[dict[str, Any]] = []
        for bit, count in self.extra_bits_by_position.most_common(10):
            ranked_bits.append(
                {
                    "bit": int(bit),
                    "mask": f"0x{(1 << int(bit)):07X}",
                    "count": count,
                    "domain": self._bit_domain(int(bit)),
                }
            )
        return {
            "total_cases": self.total_cases,
            "exact_match": self.exact_match,
            "match_with_extra_bits": self.match_with_extra_bits,
            "state_mismatch": self.state_mismatch,
            "non_lg_or_other_protocol": self.non_lg_or_other_protocol,
            "non_hvac_flag_frame": self.non_hvac_flag_frame,
            "invalid_profile_payload": self.invalid_profile_payload,
            "detected_encodings": dict(self.detected_encodings),
            "declared_encodings": dict(self.declared_encodings),
            "ranked": {
                "top_state_mismatch_models": self._top(self.state_mismatch_by_model, 10),
                "top_state_mismatch_modes": self._top(self.state_mismatch_by_mode, 10),
                "top_state_mismatch_profiles": self._top(
                    self.state_mismatch_by_profile, 10
                ),
                "top_extra_command_word_pairs": self._top(
                    self.extra_bits_by_command_pair, 10
                ),
                "top_extra_diff_masks": self._top(self.extra_bits_by_diff_mask, 10),
                "top_extra_bits": ranked_bits,
                "priority_feature_groups": self._top(self.extra_bits_domain, 10),
            },
            "samples": self.samples,
        }


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


def _expected_lg_state_from_profile(
    action_norm: str, fan_norm: str, expected_temp: float
) -> tuple[str, str, float]:
    """Normalize known LG profile semantics to protocol-level state expectations.

    LG profile matrices often store synthetic temperatures for modes where the
    protocol encodes fixed values:
    - dry mode commonly enforces temp 24 C;
    - fan_only mode commonly enforces temp 18 C.
    """
    if action_norm == "dry":
        return "dry", fan_norm, 24.0
    if action_norm == "fan_only":
        return "fan_only", fan_norm, 18.0
    return action_norm, fan_norm, expected_temp


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
            declared_encoding = str(doc.get("commandsEncoding", "unknown")).strip().lower()
            summary.declared_encodings[declared_encoding] += 1
            commands = doc.get("commands") or {}
            if not isinstance(commands, dict):
                continue
            models = [str(m) for m in (doc.get("supportedModels") or [])]
            if not models:
                models = ["<unknown_model>"]

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
                            decoded_payload = decode_ir_payload_auto(raw_payload)
                            summary.detected_encodings[decoded_payload.source_encoding] += 1
                            raw = decoded_payload.raw_timings
                            b64 = encode_raw_to_tuya_base64(raw)
                            raw_roundtrip = decode_tuya_base64_to_raw(b64)
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
                            result.hvac_mode
                            == _expected_lg_state_from_profile(
                                action_norm, fan_norm, expected_temp
                            )[0]
                            and result.fan_mode
                            == _expected_lg_state_from_profile(
                                action_norm, fan_norm, expected_temp
                            )[1]
                            and result.temperature_c
                            == _expected_lg_state_from_profile(
                                action_norm, fan_norm, expected_temp
                            )[2]
                        ):
                            summary.add(
                                "state_mismatch",
                                (
                                    f"{path.name}:{action_norm}:{fan_norm}:{expected_temp}"
                                    f"->decoded({result.hvac_mode},{result.fan_mode},{result.temperature_c})"
                                ),
                            )
                            for model in models:
                                summary.state_mismatch_by_model[model] += 1
                            summary.state_mismatch_by_mode[f"{action_norm}:{fan_norm}"] += 1
                            summary.state_mismatch_by_profile[path.name] += 1
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
                            diff_mask = (code ^ canonical) & 0x0FFFFFFF
                            cmd_code = (code >> 4) & 0xFFFF
                            cmd_canonical = (canonical >> 4) & 0xFFFF
                            summary.extra_bits_by_command_pair[
                                f"0x{cmd_code:04X}->0x{cmd_canonical:04X}"
                            ] += 1
                            summary.extra_bits_by_diff_mask[f"0x{diff_mask:07X}"] += 1
                            for bit in range(28):
                                if (diff_mask >> bit) & 0x1:
                                    summary.extra_bits_by_position[bit] += 1
                                    summary.extra_bits_domain[
                                        AuditSummary._bit_domain(bit)
                                    ] += 1
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

