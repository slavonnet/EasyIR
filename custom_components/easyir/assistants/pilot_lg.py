"""Pilot LG-only assistant flows: auto-detect from one frame, guided pairing scoring.

These functions are intentionally UI-free and deterministic for unit tests.
Confidence uses a fixed 0..1000 scale (see *_CONF constants).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal

from ..protocols.lg_p12rk.engine import (
    LG_SIGNATURE,
    decode_lg_ac_frame,
    encode_lg_ac_frame,
    valid_checksum,
)

# Fixed 0..1000 confidence scale (stable API for tests and callers).
LG_DECODE_FULL: Final[int] = 1000
LG_DECODE_CHECKSUM_FAIL: Final[int] = 280
LG_DECODE_WRONG_SIGNATURE: Final[int] = 120
LG_DECODE_EMPTY: Final[int] = 0

# Guided pairing weights (fixed; no ML).
_GUIDED_YES: Final[int] = 350
_GUIDED_NO: Final[int] = -260
_GUIDED_SKIP: Final[int] = 0

_GUIDED_ACCEPT_AT: Final[int] = 700
_GUIDED_REJECT_AT: Final[int] = -520

LgPilotBranch = Literal[
    "empty_code",
    "wrong_signature",
    "checksum_fail",
    "decoded_ok",
]

GuidedPairingVerdict = Literal["accept", "reject", "inconclusive"]


@dataclass(frozen=True)
class LgPilotAutoDetectResult:
    """Outcome of a single-frame LG pilot auto-detect attempt."""

    accepted: bool
    confidence: int
    branch: LgPilotBranch
    protocol_id: str | None
    state: dict[str, Any] | None


def _state_to_dict(code: int, st: Any) -> dict[str, Any]:
    return {
        "power_on": st.power_on,
        "hvac_mode": st.hvac_mode,
        "temperature_c": st.temperature_c,
        "fan_mode": st.fan_mode,
        "is_off_command": st.is_off_command,
        "raw_code": st.raw_code,
        "captured_code_masked": int(code) & 0x0FFFFFFF,
    }


def lg_pilot_auto_detect(captured_code: int) -> LgPilotAutoDetectResult:
    """Decode one LG28-style frame; accept only high-confidence LG pilot paths."""
    code = int(captured_code) & 0x0FFFFFFF
    if code == 0:
        return LgPilotAutoDetectResult(
            accepted=False,
            confidence=LG_DECODE_EMPTY,
            branch="empty_code",
            protocol_id=None,
            state=None,
        )

    sign = (code >> 20) & 0xFF
    if sign != LG_SIGNATURE:
        return LgPilotAutoDetectResult(
            accepted=False,
            confidence=LG_DECODE_WRONG_SIGNATURE,
            branch="wrong_signature",
            protocol_id=None,
            state=None,
        )

    if not valid_checksum(code):
        return LgPilotAutoDetectResult(
            accepted=False,
            confidence=LG_DECODE_CHECKSUM_FAIL,
            branch="checksum_fail",
            protocol_id=None,
            state=None,
        )

    st = decode_lg_ac_frame(code)
    return LgPilotAutoDetectResult(
        accepted=True,
        confidence=LG_DECODE_FULL,
        branch="decoded_ok",
        protocol_id="lg_p12rk",
        state=_state_to_dict(code, st),
    )


def default_lg_guided_probe_plan() -> list[tuple[str, int]]:
    """Ordered probe ids and LG IR codes (28-bit) for no-remote guided pairing."""
    return [
        (
            "baseline_cool_24_auto",
            encode_lg_ac_frame(
                power_on=True,
                hvac_mode="cool",
                temperature_c=24,
                fan_mode="auto",
            ),
        ),
        (
            "power_off",
            encode_lg_ac_frame(
                power_on=False,
                hvac_mode="off",
                temperature_c=24,
                fan_mode="auto",
            ),
        ),
        (
            "fan_high_cool_22",
            encode_lg_ac_frame(
                power_on=True,
                hvac_mode="cool",
                temperature_c=22,
                fan_mode="high",
            ),
        ),
    ]


def lg_pilot_guided_pairing_verdict(
    responses: dict[str, str],
) -> tuple[int, GuidedPairingVerdict]:
    """Score user feedback per probe id; unknown feedback counts as skip.

    Returns (aggregate_score, verdict).
    """
    total = 0
    for _probe_id, raw in responses.items():
        key = str(raw).strip().lower()
        if key == "yes":
            total += _GUIDED_YES
        elif key == "no":
            total += _GUIDED_NO
        elif key == "skip":
            total += _GUIDED_SKIP
        else:
            total += _GUIDED_SKIP

    if total >= _GUIDED_ACCEPT_AT:
        return total, "accept"
    if total <= _GUIDED_REJECT_AT:
        return total, "reject"
    return total, "inconclusive"
