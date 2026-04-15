"""Deterministic assistant flows (pilot slices, backend-first)."""

from .pilot_lg import (
    GuidedPairingVerdict,
    LgPilotAutoDetectResult,
    default_lg_guided_probe_plan,
    lg_pilot_auto_detect,
    lg_pilot_guided_pairing_verdict,
)

__all__ = [
    "GuidedPairingVerdict",
    "LgPilotAutoDetectResult",
    "default_lg_guided_probe_plan",
    "lg_pilot_auto_detect",
    "lg_pilot_guided_pairing_verdict",
]
