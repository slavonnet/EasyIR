"""Helpers for profile -> Tuya TS1201 encoding."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

_PROFILE_CACHE: dict[str, tuple[int, dict[str, Any]]] = {}


def _to_u16(value: int) -> int:
    """Convert signed timing value to uint16 range."""
    absolute = abs(int(value))
    return min(absolute, 0xFFFF)


def encode_raw_to_tuya_base64(raw_timings: list[int]) -> str:
    """Encode alternating mark/space timings to Tuya TS1201 payload."""
    payload_bytes: list[int] = []
    for timing in raw_timings:
        val = _to_u16(timing)
        payload_bytes.extend((val & 0xFF, (val >> 8) & 0xFF))

    encoded: list[int] = []
    for i in range(0, len(payload_bytes), 32):
        chunk = payload_bytes[i : i + 32]
        encoded.append(len(chunk) - 1)
        encoded.extend(chunk)

    return base64.b64encode(bytes(encoded)).decode()


def _parse_raw(raw: Any) -> list[int]:
    """Parse raw timings from profile (JSON string or embedded array)."""
    if isinstance(raw, (list, tuple)):
        return [int(x) for x in raw]
    if raw is None:
        raise ValueError("Command raw payload is null")
    if not isinstance(raw, str):
        raise ValueError(
            f"Command raw must be a string or list, got {type(raw).__name__}"
        )
    stripped = raw.strip()
    if not stripped:
        raise ValueError(
            "Command raw payload is empty (this profile has no IR code for this key)"
        )
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as err:
        raise ValueError(f"Invalid command raw JSON: {err}") from err
    if not isinstance(value, list):
        raise ValueError("Command raw must decode to a JSON array of integers")
    return [int(x) for x in value]


def _load_profile_document(path: str) -> dict[str, Any]:
    """Load full profile JSON with mtime-based caching (commands + metadata)."""
    file_path = Path(path)
    mtime_ns = file_path.stat().st_mtime_ns

    cached = _PROFILE_CACHE.get(path)
    if cached is not None and cached[0] == mtime_ns:
        return cached[1]

    data = json.loads(file_path.read_text(encoding="utf-8"))
    _PROFILE_CACHE[path] = (mtime_ns, data)
    return data


def _load_commands(path: str) -> dict[str, Any]:
    """Return the `commands` subtree from a cached profile document."""
    return _load_profile_document(path)["commands"]


def clear_profile_cache() -> None:
    """Clear profile cache (for tests and reloads)."""
    _PROFILE_CACHE.clear()


def _normalize_fan_key(fan_mode: str) -> str:
    """Map HA-style fan names to common profile keys."""
    aliases = {"medium": "mid"}
    return aliases.get(fan_mode, fan_mode)


def _normalize_hvac_action(action: str, hvac_mode: str | None) -> str:
    """Prefer explicit hvac_mode to avoid action/hvac mismatch in profile lookup."""
    hvac = str(hvac_mode).strip().lower() if hvac_mode is not None else ""
    if hvac in {"cool", "dry", "fan_only", "auto", "heat"}:
        return hvac
    return str(action).strip().lower()


def resolve_profile_raw(
    path: str,
    action: str,
    hvac_mode: str | None = None,
    fan_mode: str | None = None,
    temperature: int | None = None,
) -> list[int]:
    """Resolve profile command to raw timing array."""
    try:
        from .protocols.lg_universal.engine import (
            LG_CMD_AUTO_CLEAN_OFF,
            LG_CMD_AUTO_CLEAN_ON,
            LG_CMD_ENERGY_SAVING_OFF,
            LG_CMD_ENERGY_SAVING_ON,
            LG_CMD_JET_ON,
            LG_CMD_LIGHT,
            LG_CMD_SWING_OFF,
            LG_CMD_SWING_ON,
            LG_CMD_WALL_SWING_OFF,
            LG_CMD_WALL_SWING_ON,
            encode_lg_command16,
            encode_lg_ac_frame_universal,
            lg_ac_raw_timings_from_code,
            profile_uses_lg_universal_encoder,
        )
    except ImportError:
        repo_root = Path(__file__).resolve().parent.parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from custom_components.easyir.protocols.lg_universal.engine import (
            LG_CMD_AUTO_CLEAN_OFF,
            LG_CMD_AUTO_CLEAN_ON,
            LG_CMD_ENERGY_SAVING_OFF,
            LG_CMD_ENERGY_SAVING_ON,
            LG_CMD_JET_ON,
            LG_CMD_LIGHT,
            LG_CMD_SWING_OFF,
            LG_CMD_SWING_ON,
            LG_CMD_WALL_SWING_OFF,
            LG_CMD_WALL_SWING_ON,
            encode_lg_command16,
            encode_lg_ac_frame_universal,
            lg_ac_raw_timings_from_code,
            profile_uses_lg_universal_encoder,
        )

    doc = _load_profile_document(path)
    if profile_uses_lg_universal_encoder(doc):
        normalized_action = str(action).strip().lower()
        special_actions: dict[str, tuple[int, str]] = {
            "energy_saving_on": (LG_CMD_ENERGY_SAVING_ON, "energy_saving"),
            "energy_saving_off": (LG_CMD_ENERGY_SAVING_OFF, "energy_saving"),
            "jet_on": (LG_CMD_JET_ON, "jet"),
            "wall_swing_on": (LG_CMD_WALL_SWING_ON, "wall_swing"),
            "wall_swing_off": (LG_CMD_WALL_SWING_OFF, "wall_swing"),
            "swing_on": (LG_CMD_SWING_ON, "swing"),
            "swing_off": (LG_CMD_SWING_OFF, "swing"),
            "auto_clean_on": (LG_CMD_AUTO_CLEAN_ON, "auto_clean"),
            "auto_clean_off": (LG_CMD_AUTO_CLEAN_OFF, "auto_clean"),
            "light": (LG_CMD_LIGHT, "light"),
        }

        if normalized_action in special_actions:
            profile_flags = {
                str(x).strip().lower() for x in (doc.get("easyir_feature_flags") or [])
            }
            command16, required_flag = special_actions[normalized_action]
            if required_flag not in profile_flags:
                raise ValueError(
                    f"Action '{action}' requires profile feature flag '{required_flag}'"
                )
            return lg_ac_raw_timings_from_code(encode_lg_command16(command16))

        if normalized_action not in ("off", "cool", "dry", "heat", "fan_only", "auto"):
            raise ValueError(
                f"Action '{action}' is not supported by LG universal encoder in MVP send path"
            )
        if normalized_action == "off":
            code = encode_lg_ac_frame_universal(
                power_on=False,
                hvac_mode="off",
                temperature_c=24,
                fan_mode="auto",
            )
            return lg_ac_raw_timings_from_code(code)

        if hvac_mode is None or fan_mode is None or temperature is None:
            raise ValueError(
                "For non-off actions, provide hvac_mode, fan_mode and temperature"
            )
        op_modes = {str(x).strip().lower() for x in (doc.get("operationModes") or [])}
        fan_modes = {str(x).strip().lower() for x in (doc.get("fanModes") or [])}
        mode_key = str(hvac_mode).strip().lower()
        fan_key = _normalize_fan_key(str(fan_mode).strip().lower())
        if op_modes and mode_key not in op_modes:
            raise ValueError(
                f"HVAC mode '{hvac_mode}' is not supported by this LG profile metadata"
            )
        if fan_modes and fan_key not in fan_modes:
            raise ValueError(
                f"Fan mode '{fan_mode}' is not supported by this LG profile metadata"
            )
        tmin = int(float(doc.get("minTemperature", 16)))
        tmax = int(float(doc.get("maxTemperature", 32)))
        temp_i = int(temperature)
        if temp_i < tmin or temp_i > tmax:
            raise ValueError(
                f"Temperature {temp_i} out of profile range {tmin}..{tmax}"
            )
        code = encode_lg_ac_frame_universal(
            power_on=True,
            hvac_mode=mode_key,
            temperature_c=temp_i,
            fan_mode=fan_key,
        )
        return lg_ac_raw_timings_from_code(code)

    commands = doc["commands"]

    action_key = str(action).strip().lower()
    if action_key == "off":
        return _parse_raw(commands["off"])

    if hvac_mode is None or fan_mode is None or temperature is None:
        raise ValueError(
            "For non-off actions, provide hvac_mode, fan_mode and temperature"
        )

    profile_action = _normalize_hvac_action(action_key, hvac_mode)
    if profile_action not in commands:
        raise ValueError(
            f"Action '{profile_action}' not found in profile commands "
            f"(requested action='{action}', hvac_mode='{hvac_mode}')"
        )

    fan_key = _normalize_fan_key(fan_mode)
    if fan_key not in commands[profile_action]:
        raise ValueError(
            f"Fan mode '{fan_mode}' not found under action '{profile_action}' "
            f"(tried '{fan_key}')"
        )
    raw = commands[profile_action][fan_key][str(temperature)]
    return _parse_raw(raw)
