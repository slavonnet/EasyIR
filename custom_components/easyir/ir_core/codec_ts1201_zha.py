"""Transport encoder: canonical timings -> Tuya TS1201 ZHA `code` parameter (base64)."""

from __future__ import annotations

from typing import Any

from ..helpers import encode_raw_to_tuya_base64
from .model import CanonicalIRFrame


class Ts1201ZhaBase64Encoder:
    """Wraps legacy `encode_raw_to_tuya_base64` without changing its algorithm."""

    transport_id = "ts1201_zha"

    def encode(self, frame: CanonicalIRFrame) -> Any:
        return encode_raw_to_tuya_base64(self._timings_for_encode(frame))

    def _timings_for_encode(self, frame: CanonicalIRFrame) -> list[int]:
        return list(frame.timings)
