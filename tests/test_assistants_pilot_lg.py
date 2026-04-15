"""Branch and confidence tests for pilot LG assistant flows (deterministic)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_components"))

from custom_components.easyir.assistants.pilot_lg import (
    LG_DECODE_CHECKSUM_FAIL,
    LG_DECODE_EMPTY,
    LG_DECODE_FULL,
    LG_DECODE_WRONG_SIGNATURE,
    default_lg_guided_probe_plan,
    lg_pilot_auto_detect,
    lg_pilot_guided_pairing_verdict,
)
from custom_components.easyir.protocols.lg_p12rk.engine import (
    apply_checksum,
    encode_lg_ac_frame,
    valid_checksum,
)


class TestLgPilotAutoDetect(unittest.TestCase):
    def test_empty_code(self) -> None:
        r = lg_pilot_auto_detect(0)
        self.assertFalse(r.accepted)
        self.assertEqual(r.branch, "empty_code")
        self.assertEqual(r.confidence, LG_DECODE_EMPTY)
        self.assertIsNone(r.protocol_id)

    def test_wrong_signature(self) -> None:
        # Valid checksum nibble but wrong signature byte.
        body = 0x12 << 20 | (0 << 18) | (0 << 12) | (9 << 8) | (5 << 4)
        code = apply_checksum(body)
        r = lg_pilot_auto_detect(code)
        self.assertFalse(r.accepted)
        self.assertEqual(r.branch, "wrong_signature")
        self.assertEqual(r.confidence, LG_DECODE_WRONG_SIGNATURE)

    def test_checksum_fail(self) -> None:
        good = encode_lg_ac_frame(
            power_on=True,
            hvac_mode="cool",
            temperature_c=24,
            fan_mode="auto",
        )
        self.assertTrue(valid_checksum(good))
        bad = good ^ 0x10
        r = lg_pilot_auto_detect(bad)
        self.assertFalse(r.accepted)
        self.assertEqual(r.branch, "checksum_fail")
        self.assertEqual(r.confidence, LG_DECODE_CHECKSUM_FAIL)

    def test_decode_ok_accepted(self) -> None:
        code = encode_lg_ac_frame(
            power_on=True,
            hvac_mode="cool",
            temperature_c=24,
            fan_mode="auto",
        )
        r = lg_pilot_auto_detect(code)
        self.assertTrue(r.accepted)
        self.assertEqual(r.branch, "decoded_ok")
        self.assertEqual(r.confidence, LG_DECODE_FULL)
        self.assertEqual(r.protocol_id, "lg_p12rk")
        assert r.state is not None
        self.assertTrue(r.state["power_on"])
        self.assertEqual(r.state["hvac_mode"], "cool")
        self.assertEqual(r.state["temperature_c"], 24)


class TestGuidedPairingVerdict(unittest.TestCase):
    def test_accept_boundary_two_yes(self) -> None:
        score, v = lg_pilot_guided_pairing_verdict({"a": "yes", "b": "yes"})
        self.assertEqual(score, 700)
        self.assertEqual(v, "accept")

    def test_reject_boundary_two_no(self) -> None:
        score, v = lg_pilot_guided_pairing_verdict({"a": "no", "b": "no"})
        self.assertEqual(score, -520)
        self.assertEqual(v, "reject")

    def test_inconclusive_mixed(self) -> None:
        score, v = lg_pilot_guided_pairing_verdict({"a": "yes", "b": "no"})
        self.assertEqual(score, 90)
        self.assertEqual(v, "inconclusive")

    def test_unknown_feedback_treated_as_skip(self) -> None:
        score, v = lg_pilot_guided_pairing_verdict({"a": "maybe", "b": "unknown"})
        self.assertEqual(score, 0)
        self.assertEqual(v, "inconclusive")

    def test_skip_neutral(self) -> None:
        score, v = lg_pilot_guided_pairing_verdict({"a": "skip", "b": "skip"})
        self.assertEqual(score, 0)
        self.assertEqual(v, "inconclusive")


class TestDefaultProbePlan(unittest.TestCase):
    def test_plan_is_deterministic_three_probes(self) -> None:
        p1 = default_lg_guided_probe_plan()
        p2 = default_lg_guided_probe_plan()
        self.assertEqual(p1, p2)
        self.assertEqual(len(p1), 3)
        for _pid, code in p1:
            self.assertTrue(valid_checksum(code))
