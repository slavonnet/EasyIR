"""Transport encoder: canonical timings -> Tuya learn-code base64 payload."""

from __future__ import annotations

from typing import Any

from ..helpers import encode_raw_to_tuya_learn_base64
from .model import CanonicalIRFrame


class TuyaLearnBase64Encoder:
    """Encode canonical timings for Tuya-learn IR payloads (FastLZ wrapped base64)."""

    transport_id = "tuya_learn_base64"

    def encode(self, frame: CanonicalIRFrame) -> Any:
        return encode_raw_to_tuya_learn_base64(self._timings_for_encode(frame))

    def _timings_for_encode(self, frame: CanonicalIRFrame) -> list[int]:
        return list(frame.timings)
