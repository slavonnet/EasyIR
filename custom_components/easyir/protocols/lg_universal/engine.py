"""Universal LG AC 28-bit frame engine (encode, decode, raw timing synthesis).

Bit packing matches the existing EasyIR pilot encoder (IRremoteESP8266 IRLgAc)
and is aligned with the LGProtocol union documented in Arduino-IRremote ac_LG.h.

References:
  https://raw.githubusercontent.com/Arduino-IRremote/Arduino-IRremote/refs/heads/master/src/ac_LG.h
  https://raw.githubusercontent.com/Arduino-IRremote/Arduino-IRremote/refs/heads/master/src/ac_LG.hpp
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

LG_SIGNATURE: Final[int] = 0x88
LG_POWER_ON: Final[int] = 0
LG_POWER_OFF: Final[int] = 3
LG_MODE_COOL: Final[int] = 0
LG_MODE_DRY: Final[int] = 1
LG_MODE_FAN: Final[int] = 2
LG_MODE_AUTO: Final[int] = 3
LG_MODE_HEAT: Final[int] = 4
LG_FAN_AUTO: Final[int] = 5
LG_FAN_LOW: Final[int] = 1
LG_FAN_MEDIUM: Final[int] = 2
LG_FAN_HIGH: Final[int] = 4
LG_FAN_LOWEST: Final[int] = 0
LG_TEMP_ADJUST: Final[int] = 15
LG_OFF_COMMAND: Final[int] = 0x88C0051
LG_CMD_ENERGY_SAVING_ON: Final[int] = 0x1004
LG_CMD_ENERGY_SAVING_OFF: Final[int] = 0x1005
LG_CMD_JET_ON: Final[int] = 0x1008
LG_CMD_WALL_SWING_ON: Final[int] = 0x1314
LG_CMD_WALL_SWING_OFF: Final[int] = 0x1315
LG_CMD_SWING_ON: Final[int] = 0x1316
LG_CMD_SWING_OFF: Final[int] = 0x1317
LG_CMD_TIMER_ON_BASE: Final[int] = 0x8000
LG_CMD_TIMER_OFF_BASE: Final[int] = 0x9000
LG_CMD_SLEEP_BASE: Final[int] = 0xA000
LG_CMD_CLEAR_ALL: Final[int] = 0xB000
LG_CMD_POWER_DOWN: Final[int] = 0xC005
LG_CMD_LIGHT: Final[int] = 0xC00A
LG_CMD_AUTO_CLEAN_ON: Final[int] = 0xC00B
LG_CMD_AUTO_CLEAN_OFF: Final[int] = 0xC00C
LG_CMD_IONIZER_OFF: Final[int] = 0xC02F
LG_CMD_IONIZER_ON: Final[int] = 0xC039

# Nominal LG AC carrier timings (Arduino-IRremote ac_LG.hpp comments, type AKB73315611).
HEADER_MARK_US: Final[int] = 8900
HEADER_SPACE_US: Final[int] = 4150
BIT_MARK_US: Final[int] = 500
BIT_ZERO_SPACE_US: Final[int] = 550
BIT_ONE_SPACE_US: Final[int] = 1580
TRAILER_SPACE_US: Final[int] = 101502


def _sum_nibbles16(value: int) -> int:
    acc = 0
    for _ in range(4):
        acc += value & 0xF
        value >>= 4
    return acc & 0xF


def calc_checksum(state: int) -> int:
    command = (state >> 4) & 0xFFFF
    return _sum_nibbles16(command)


def valid_checksum(code: int) -> bool:
    return (code & 0xF) == calc_checksum(code)


def pack_body(sign: int, power: int, mode: int, temp_raw: int, fan: int) -> int:
    return (
        (sign & 0xFF) << 20
        | (power & 0x3) << 18
        | (mode & 0x7) << 12
        | (temp_raw & 0xF) << 8
        | (fan & 0xF) << 4
    )


def apply_checksum(body_without_checksum: int) -> int:
    cleared = body_without_checksum & 0xFFFFFFF0
    return cleared | calc_checksum(cleared)


def _native_fan_to_ha(fan: int) -> str:
    if fan == LG_FAN_AUTO:
        return "auto"
    if fan == LG_FAN_LOW:
        return "low"
    if fan == LG_FAN_MEDIUM:
        return "mid"
    if fan == LG_FAN_HIGH:
        return "high"
    if fan == LG_FAN_LOWEST:
        return "low"
    return "unknown"


def _ha_fan_to_native(fan_mode: str) -> int:
    aliases = {"medium": "mid"}
    key = aliases.get(fan_mode, fan_mode)
    if key == "auto":
        return LG_FAN_AUTO
    if key == "low":
        return LG_FAN_LOW
    if key == "mid":
        return LG_FAN_MEDIUM
    if key == "high":
        return LG_FAN_HIGH
    return LG_FAN_AUTO


def _native_mode_to_ha(mode: int) -> str:
    return {
        LG_MODE_COOL: "cool",
        LG_MODE_DRY: "dry",
        LG_MODE_FAN: "fan_only",
        LG_MODE_AUTO: "auto",
        LG_MODE_HEAT: "heat",
    }.get(mode, "unknown")


def _ha_mode_to_native(hvac_mode: str) -> int:
    if hvac_mode == "cool":
        return LG_MODE_COOL
    if hvac_mode == "dry":
        return LG_MODE_DRY
    if hvac_mode == "fan_only":
        return LG_MODE_FAN
    if hvac_mode == "auto":
        return LG_MODE_AUTO
    if hvac_mode == "heat":
        return LG_MODE_HEAT
    return LG_MODE_COOL


def encode_lg_ac_frame_universal(
    *,
    power_on: bool,
    hvac_mode: str,
    temperature_c: int,
    fan_mode: str,
) -> int:
    """Build a 28-bit LG AC state frame with a valid checksum nibble."""
    if not power_on or hvac_mode == "off":
        return LG_OFF_COMMAND
    temp = max(16, min(30, int(temperature_c)))
    temp_raw = temp - LG_TEMP_ADJUST
    mode = _ha_mode_to_native(hvac_mode)
    fan = _ha_fan_to_native(fan_mode)
    partial = pack_body(LG_SIGNATURE, LG_POWER_ON, mode, temp_raw, fan)
    return apply_checksum(partial)


def encode_lg_command16(command16: int) -> int:
    """Encode LG 16-bit command word (ac_LG.h constants) into 28-bit frame."""
    body = ((LG_SIGNATURE & 0xFF) << 20) | ((command16 & 0xFFFF) << 4)
    return apply_checksum(body)


def lg_ac_raw_timings_from_code(code: int) -> list[int]:
    """Expand a 28-bit LG AC logical code to alternating mark/space microseconds."""
    code &= 0x0FFFFFFF
    timings: list[int] = [HEADER_MARK_US, -HEADER_SPACE_US]
    for bit_pos in range(27, -1, -1):
        bit = (code >> bit_pos) & 1
        timings.append(BIT_MARK_US)
        timings.append(-(BIT_ONE_SPACE_US if bit else BIT_ZERO_SPACE_US))
    timings.append(-TRAILER_SPACE_US)
    return timings


@dataclass(frozen=True)
class LgDecodeResult:
    """Strict decode outcome: HVAC delta, extracted flags, and validation metadata."""

    ok: bool
    error: str | None
    power_on: bool
    hvac_mode: str
    temperature_c: float | None
    fan_mode: str
    raw_code: int
    is_off_command: bool
    feature_flags: dict[str, Any] = field(default_factory=dict)
    checksum_valid: bool = False
    signature_ok: bool = False


def _command_word_from_frame(code: int) -> int:
    """LG command16 lives in bits 4..19 of the 28-bit frame."""
    return (code >> 4) & 0xFFFF


def _decode_feature_flags(command16: int) -> dict[str, Any]:
    """Map known non-state LG command words (ac_LG.h) to structured flags."""
    flags: dict[str, Any] = {"command_word": f"0x{command16:04X}"}
    # State command words (mode/temp/fan) are in lower command space.
    if 0x0000 <= command16 <= 0x0FFF:
        flags["mode_temp_fan"] = True
        return flags
    # Named constants from ac_LG.h
    if command16 == LG_CMD_POWER_DOWN:
        flags["lg_command"] = "power_down"
    elif command16 == LG_CMD_ENERGY_SAVING_ON:
        flags["energy_saving"] = True
    elif command16 == LG_CMD_ENERGY_SAVING_OFF:
        flags["energy_saving"] = False
    elif command16 == LG_CMD_JET_ON:
        flags["jet"] = True
    elif command16 == LG_CMD_WALL_SWING_ON:
        flags["wall_swing"] = True
    elif command16 == LG_CMD_WALL_SWING_OFF:
        flags["wall_swing"] = False
    elif command16 == LG_CMD_SWING_ON:
        flags["swing"] = True
    elif command16 == LG_CMD_SWING_OFF:
        flags["swing"] = False
    elif command16 == LG_CMD_LIGHT:
        flags["light_toggle"] = True
    elif command16 == LG_CMD_AUTO_CLEAN_ON:
        flags["auto_clean"] = True
    elif command16 == LG_CMD_AUTO_CLEAN_OFF:
        flags["auto_clean"] = False
    elif command16 == LG_CMD_IONIZER_ON:
        flags["ionizer"] = True
    elif command16 == LG_CMD_IONIZER_OFF:
        flags["ionizer"] = False
    elif LG_CMD_TIMER_ON_BASE <= command16 <= 0x8FFF:
        flags["timer_on_minutes"] = command16 & 0x0FFF
    elif LG_CMD_TIMER_OFF_BASE <= command16 <= 0x9FFF:
        flags["timer_off_minutes"] = command16 & 0x0FFF
    elif LG_CMD_SLEEP_BASE <= command16 <= 0xAFFF:
        flags["sleep_minutes"] = command16 & 0x0FFF
    elif LG_CMD_CLEAR_ALL <= command16 <= 0xBFFF:
        flags["clear_timers"] = True
    else:
        flags["lg_command"] = "unknown"
    return flags


def _required_supported_flags(feature_flags: dict[str, Any]) -> frozenset[str]:
    if feature_flags.get("power_off"):
        return frozenset({"power_off"})
    if feature_flags.get("mode_temp_fan"):
        return frozenset({"mode_temp_fan"})
    if "energy_saving" in feature_flags:
        return frozenset({"energy_saving"})
    if feature_flags.get("jet"):
        return frozenset({"jet"})
    if "wall_swing" in feature_flags:
        return frozenset({"wall_swing"})
    if "swing" in feature_flags:
        return frozenset({"swing"})
    if feature_flags.get("light_toggle"):
        return frozenset({"light"})
    if "auto_clean" in feature_flags:
        return frozenset({"auto_clean"})
    if "ionizer" in feature_flags:
        return frozenset({"ionizer"})
    if "timer_on_minutes" in feature_flags:
        return frozenset({"timer_on"})
    if "timer_off_minutes" in feature_flags:
        return frozenset({"timer_off"})
    if "sleep_minutes" in feature_flags:
        return frozenset({"sleep"})
    if feature_flags.get("clear_timers"):
        return frozenset({"clear_timers"})
    return frozenset()


def decode_lg_ac_strict(
    code: int,
    *,
    supported_flags: frozenset[str] | None = None,
) -> LgDecodeResult:
    """Decode with explicit checksum + signature validation and flag extraction contract."""
    code &= 0x0FFFFFFF
    sig = (code >> 20) & 0xFF
    signature_ok = sig == LG_SIGNATURE
    checksum_valid = valid_checksum(code)

    if not signature_ok:
        return LgDecodeResult(
            ok=False,
            error="invalid_signature",
            power_on=False,
            hvac_mode="unknown",
            temperature_c=None,
            fan_mode="auto",
            raw_code=code,
            is_off_command=False,
            feature_flags={},
            checksum_valid=checksum_valid,
            signature_ok=False,
        )

    if code == LG_OFF_COMMAND:
        ff = {"power_off": True}
        if supported_flags is not None and not supported_flags.issuperset({"power_off"}):
            return LgDecodeResult(
                ok=False,
                error="flag_not_supported:power_off",
                power_on=False,
                hvac_mode="off",
                temperature_c=None,
                fan_mode="auto",
                raw_code=code,
                is_off_command=True,
                feature_flags=ff,
                checksum_valid=checksum_valid,
                signature_ok=True,
            )
        return LgDecodeResult(
            ok=True,
            error=None,
            power_on=False,
            hvac_mode="off",
            temperature_c=None,
            fan_mode="auto",
            raw_code=code,
            is_off_command=True,
            feature_flags=ff,
            checksum_valid=checksum_valid,
            signature_ok=True,
        )

    if not checksum_valid:
        command16 = _command_word_from_frame(code)
        return LgDecodeResult(
            ok=False,
            error="checksum_mismatch",
            power_on=False,
            hvac_mode="unknown",
            temperature_c=None,
            fan_mode="auto",
            raw_code=code,
            is_off_command=False,
            feature_flags=_decode_feature_flags(command16),
            checksum_valid=False,
            signature_ok=True,
        )

    command16 = _command_word_from_frame(code)
    ff = _decode_feature_flags(command16)
    required_flags = _required_supported_flags(ff)
    if supported_flags is not None:
        if required_flags and not supported_flags.issuperset(required_flags):
            missing = sorted(required_flags - supported_flags)
            miss = missing[0] if missing else "unknown"
            return LgDecodeResult(
                ok=False,
                error=f"flag_not_supported:{miss}",
                power_on=False,
                hvac_mode="unknown",
                temperature_c=None,
                fan_mode="auto",
                raw_code=code,
                is_off_command=False,
                feature_flags=ff,
                checksum_valid=True,
                signature_ok=True,
            )

    if ff.get("lg_command") == "unknown":
        return LgDecodeResult(
            ok=False,
            error="unknown_command_word",
            power_on=False,
            hvac_mode="unknown",
            temperature_c=None,
            fan_mode="auto",
            raw_code=code,
            is_off_command=False,
            feature_flags=ff,
            checksum_valid=True,
            signature_ok=True,
        )

    if not ff.get("mode_temp_fan"):
        return LgDecodeResult(
            ok=True,
            error=None,
            power_on=False,
            hvac_mode="unknown",
            temperature_c=None,
            fan_mode="auto",
            raw_code=code,
            is_off_command=False,
            feature_flags=ff,
            checksum_valid=True,
            signature_ok=True,
        )

    power = (code >> 18) & 0x3
    mode = (code >> 12) & 0x7
    temp_raw = (code >> 8) & 0xF
    fan = (code >> 4) & 0xF
    power_on = power == LG_POWER_ON
    temp_c: float | None = float(temp_raw + LG_TEMP_ADJUST) if power_on else None
    ha_mode = "off" if not power_on else _native_mode_to_ha(mode)
    ha_fan = _native_fan_to_ha(fan) if power_on else "auto"

    # Strict contract: HVAC state frames must decode to known normalized enums.
    if power_on and (ha_mode == "unknown" or ha_fan == "unknown"):
        return LgDecodeResult(
            ok=False,
            error="unsupported_hvac_state",
            power_on=power_on,
            hvac_mode=ha_mode,
            temperature_c=temp_c,
            fan_mode=ha_fan,
            raw_code=code,
            is_off_command=False,
            feature_flags=ff,
            checksum_valid=True,
            signature_ok=True,
        )

    return LgDecodeResult(
        ok=True,
        error=None,
        power_on=power_on,
        hvac_mode=ha_mode,
        temperature_c=temp_c,
        fan_mode=ha_fan,
        raw_code=code,
        is_off_command=False,
        feature_flags=ff,
        checksum_valid=True,
        signature_ok=True,
    )


def load_lg_universal_descriptor() -> dict[str, Any]:
    path = Path(__file__).with_name("descriptor.json")
    return json.loads(path.read_text(encoding="utf-8"))


def profile_uses_lg_universal_encoder(data: dict[str, Any]) -> bool:
    """Return True when profile opts into synthesized LG28 timings (not combinatoric matrix)."""
    proto = str(data.get("easyir_protocol", "")).strip().lower()
    enc = str(data.get("easyir_encoding", "raw")).strip().lower()
    return proto in ("lg_universal_v1", "lg_universal") and enc == "lg28"
