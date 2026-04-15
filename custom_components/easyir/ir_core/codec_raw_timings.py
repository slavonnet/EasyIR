"""Codec: alternating mark/space microseconds carried verbatim in the canonical frame."""

from __future__ import annotations

from typing import Any

from .model import CanonicalIRFrame


class RawTimingsCodec:
    """Identity-style codec for MVP raw `raw_timings` / profile-resolved pulse trains."""

    codec_id = "raw_timings"

    def frame_from_timings(
        self,
        timings: list[int],
        *,
        carrier_frequency_hz: float | None = None,
        repeat: int = 0,
        duty_cycle: float | None = None,
        protocol_hint: str = "unknown",
        integrity_metadata: dict[str, Any] | None = None,
        decode_confidence: float | None = None,
        unknown_fields: dict[str, Any] | None = None,
    ) -> CanonicalIRFrame:
        meta = dict(integrity_metadata or ())
        meta.setdefault("codec_id", self.codec_id)
        return CanonicalIRFrame(
            timings=[int(x) for x in timings],
            carrier_frequency_hz=carrier_frequency_hz,
            repeat=int(repeat),
            duty_cycle=duty_cycle,
            protocol_hint=protocol_hint,
            integrity_metadata=meta,
            decode_confidence=decode_confidence,
            unknown_fields=dict(unknown_fields or ()),
        )

    def timings_from_frame(self, frame: CanonicalIRFrame) -> list[int]:
        return list(frame.timings)
