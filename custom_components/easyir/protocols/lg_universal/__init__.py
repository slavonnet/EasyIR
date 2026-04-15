"""Universal LG AC bit engine (28-bit frame) and profile adapter hooks."""

from .engine import (
    LgDecodeResult,
    decode_lg_ac_strict,
    encode_lg_ac_frame_universal,
    lg_ac_raw_timings_from_code,
    load_lg_universal_descriptor,
    profile_uses_lg_universal_encoder,
)

__all__ = [
    "LgDecodeResult",
    "decode_lg_ac_strict",
    "encode_lg_ac_frame_universal",
    "lg_ac_raw_timings_from_code",
    "load_lg_universal_descriptor",
    "profile_uses_lg_universal_encoder",
]
