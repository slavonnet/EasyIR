"""Pluggable IR codecs and transport payload encoders."""

from __future__ import annotations

from typing import Any, Protocol

from .model import CanonicalIRFrame


class IrCodec(Protocol):
    """Bidirectional raw timings <-> canonical frame (codec_id identifies format family)."""

    @property
    def codec_id(self) -> str:
        """Stable identifier used for registration and metadata."""

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
        """Normalize alternating mark/space microseconds into a canonical frame."""

    def timings_from_frame(self, frame: CanonicalIRFrame) -> list[int]:
        """Extract timings for encoders that operate on raw pulse trains."""


class TransportPayloadEncoder(Protocol):
    """Canonical frame -> transport-specific wire payload (e.g. ZHA cluster param)."""

    @property
    def transport_id(self) -> str:
        """Stable identifier (e.g. ts1201_zha)."""

    def encode(self, frame: CanonicalIRFrame) -> Any:
        """Return payload fragment expected by the transport send path."""


class CodecRegistry:
    """Extensible registry; service layer uses defaults without changing public service API."""

    def __init__(self) -> None:
        self._codecs: dict[str, IrCodec] = {}
        self._encoders: dict[str, TransportPayloadEncoder] = {}

    def register_codec(self, codec: IrCodec) -> None:
        self._codecs[codec.codec_id] = codec

    def register_transport_encoder(self, encoder: TransportPayloadEncoder) -> None:
        self._encoders[encoder.transport_id] = encoder

    def get_codec(self, codec_id: str) -> IrCodec:
        try:
            return self._codecs[codec_id]
        except KeyError as err:
            raise KeyError(f"Unknown IR codec: {codec_id!r}") from err

    def get_transport_encoder(self, transport_id: str) -> TransportPayloadEncoder:
        try:
            return self._encoders[transport_id]
        except KeyError as err:
            raise KeyError(f"Unknown transport encoder: {transport_id!r}") from err

    def encode_for_transport(self, transport_id: str, frame: CanonicalIRFrame) -> Any:
        return self.get_transport_encoder(transport_id).encode(frame)


def default_codec_registry() -> CodecRegistry:
    """Built-in MVP chain: raw timings passthrough + vendor/transport encoders."""
    # Local imports keep helpers optional for tests importing only model/registry.
    from .codec_broadlink import BroadlinkBase64Encoder
    from .codec_raw_timings import RawTimingsCodec
    from .codec_ts1201_zha import Ts1201ZhaBase64Encoder

    reg = CodecRegistry()
    reg.register_codec(RawTimingsCodec())
    reg.register_transport_encoder(Ts1201ZhaBase64Encoder())
    reg.register_transport_encoder(BroadlinkBase64Encoder())
    return reg
