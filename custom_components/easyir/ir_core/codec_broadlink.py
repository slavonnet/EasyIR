"""Transport encoder: canonical timings -> Broadlink-style base64 payload."""

from __future__ import annotations

from typing import Any

from ..helpers import encode_raw_to_broadlink_base64
from .model import CanonicalIRFrame


class BroadlinkBase64Encoder:
    """Encode canonical timings for Broadlink-compatible payload fields."""

    transport_id = "broadlink_base64"

    def encode(self, frame: CanonicalIRFrame) -> Any:
        return encode_raw_to_broadlink_base64(self._timings_for_encode(frame))

    def _timings_for_encode(self, frame: CanonicalIRFrame) -> list[int]:
        return list(frame.timings)
