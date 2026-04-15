"""LG AC IR frame encode/decode (IRremoteESP8266 IRLgAc / LGProtocol layout)."""

from __future__ import annotations

import json
from dataclasses import dataclass
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


def _sum_nibbles16(value: int) -> int:
    """Sum of four nibbles of the low 16 bits (IRremoteESP8266 LG AC checksum)."""
    acc = 0
    for _ in range(4):
        acc += value & 0xF
        value >>= 4
    return acc & 0xF


def calc_checksum(state: int) -> int:
    """Low nibble = sum of nibbles of the 16-bit command (bits 4..19)."""
    command = (state >> 4) & 0xFFFF
    return _sum_nibbles16(command)


def valid_checksum(state: int) -> bool:
    return (state & 0xF) == calc_checksum(state)


def pack_body(
    sign: int, power: int, mode: int, temp_raw: int, fan: int
) -> int:
    """Assemble LG AC uint32 with checksum nibble cleared (bits 0..3 = 0)."""
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


@dataclass(frozen=True)
class LgAcStateDelta:
    """Normalized state extracted from a single LG AC IR frame."""

    power_on: bool
    hvac_mode: str
    temperature_c: int | None
    fan_mode: str
    raw_code: int
    is_off_command: bool


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


def decode_lg_ac_frame(code: int) -> LgAcStateDelta:
    """Decode a 28-bit LG AC code (IRremoteESP8266 wire format)."""
    code &= 0x0FFFFFFF

    if code == LG_OFF_COMMAND:
        return LgAcStateDelta(
            power_on=False,
            hvac_mode="off",
            temperature_c=None,
            fan_mode="auto",
            raw_code=code,
            is_off_command=True,
        )

    sign = (code >> 20) & 0xFF
    power = (code >> 18) & 0x3
    mode = (code >> 12) & 0x7
    temp_raw = (code >> 8) & 0xF
    fan = (code >> 4) & 0xF

    power_on = power == LG_POWER_ON
    temp_c = temp_raw + LG_TEMP_ADJUST if power_on else None

    return LgAcStateDelta(
        power_on=power_on,
        hvac_mode="off" if not power_on else _native_mode_to_ha(mode),
        temperature_c=temp_c,
        fan_mode=_native_fan_to_ha(fan) if power_on else "auto",
        raw_code=code,
        is_off_command=False,
    )


def encode_lg_ac_frame(
    *,
    power_on: bool,
    hvac_mode: str,
    temperature_c: int,
    fan_mode: str,
) -> int:
    """Encode HA-oriented state to a 28-bit LG AC frame with valid checksum."""
    if not power_on or hvac_mode == "off":
        return LG_OFF_COMMAND

    temp = max(16, min(30, int(temperature_c)))
    temp_raw = temp - LG_TEMP_ADJUST
    mode = _ha_mode_to_native(hvac_mode)
    fan = _ha_fan_to_native(fan_mode)
    partial = pack_body(LG_SIGNATURE, LG_POWER_ON, mode, temp_raw, fan)
    return apply_checksum(partial)


def load_lg_p12rk_descriptor() -> dict[str, Any]:
    """Load bundled JSON descriptor (read-only)."""
    path = Path(__file__).with_name("descriptor.json")
    return json.loads(path.read_text(encoding="utf-8"))


def load_lg_p12rk_capabilities() -> dict[str, Any]:
    path = Path(__file__).with_name("capabilities.json")
    return json.loads(path.read_text(encoding="utf-8"))
