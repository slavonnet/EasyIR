"""Compatibility adapter: service-layer inputs -> canonical frame -> TS1201 payload."""

from __future__ import annotations

from typing import Any

from .model import CanonicalIRFrame
from .registry import CodecRegistry, default_codec_registry

_DEFAULT_TRANSPORT = "ts1201_zha"
_DEFAULT_CODEC = "raw_timings"


def encode_raw_timings_for_zha_ts1201(
    raw_timings: list[int],
    *,
    registry: CodecRegistry | None = None,
) -> tuple[CanonicalIRFrame, str]:
    """Path for `easyir.send_raw`: timings -> canonical frame -> ZHA TS1201 base64 code."""
    reg = registry or default_codec_registry()
    codec = reg.get_codec(_DEFAULT_CODEC)
    frame = codec.frame_from_timings(
        raw_timings,
        protocol_hint="raw_timings",
        integrity_metadata={"source": "easyir.send_raw"},
    )
    code = reg.encode_for_transport(_DEFAULT_TRANSPORT, frame)
    return frame, str(code)


def encode_profile_command_for_zha_ts1201(
    *,
    profile_path: str,
    action: str,
    hvac_mode: str | None,
    fan_mode: str | None,
    temperature: int | None,
    registry: CodecRegistry | None = None,
) -> tuple[CanonicalIRFrame, str]:
    """Path for `easyir.send_profile_command`: profile resolution -> frame -> base64 code."""
    # Import here to avoid circular import with helpers.
    from ..helpers import resolve_profile_raw

    reg = registry or default_codec_registry()
    raw_timings = resolve_profile_raw(
        path=profile_path,
        action=action,
        hvac_mode=hvac_mode,
        fan_mode=fan_mode,
        temperature=temperature,
    )
    codec = reg.get_codec(_DEFAULT_CODEC)
    frame = codec.frame_from_timings(
        raw_timings,
        protocol_hint="profile",
        integrity_metadata={
            "source": "easyir.send_profile_command",
            "profile_path": profile_path,
            "action": action,
        },
    )
    code = reg.encode_for_transport(_DEFAULT_TRANSPORT, frame)
    return frame, str(code)


def transcode_ir_between_transports(
    payload: Any,
    *,
    target_transport_id: str,
    source_encoding: str | None = None,
    registry: CodecRegistry | None = None,
) -> tuple[CanonicalIRFrame, Any]:
    """Decode arbitrary IR payload to canonical frame and encode for target transport."""
    from ..helpers import decode_ir_payload

    reg = registry or default_codec_registry()
    decoded = decode_ir_payload(payload, encoding=source_encoding)
    codec = reg.get_codec(_DEFAULT_CODEC)
    frame = codec.frame_from_timings(
        decoded.raw_timings,
        protocol_hint="transcode",
        integrity_metadata={
            "source": "easyir.transcode",
            "detected_encoding": decoded.source_encoding,
        },
    )
    encoded = reg.encode_for_transport(target_transport_id, frame)
    return frame, encoded
