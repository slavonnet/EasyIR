"""Canonical IR model, codec registry, and transport payload adapters (foundation layer)."""

from __future__ import annotations

from .model import CanonicalIRFrame
from .registry import CodecRegistry, IrCodec, TransportPayloadEncoder, default_codec_registry
from .service_adapter import (
    encode_profile_command_for_zha_ts1201,
    encode_raw_timings_for_zha_ts1201,
)

__all__ = [
    "CanonicalIRFrame",
    "CodecRegistry",
    "IrCodec",
    "TransportPayloadEncoder",
    "default_codec_registry",
    "encode_profile_command_for_zha_ts1201",
    "encode_raw_timings_for_zha_ts1201",
]
