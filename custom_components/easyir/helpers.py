"""Helpers for profile -> Tuya TS1201 encoding."""

from __future__ import annotations

import base64
import json
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


def _parse_raw(raw_string: str) -> list[int]:
    """Parse raw timing string from profile format."""
    value = json.loads(raw_string)
    return [int(x) for x in value]


def _load_commands(path: str) -> dict[str, Any]:
    """Load profile JSON payload with mtime-based caching."""
    file_path = Path(path)
    mtime_ns = file_path.stat().st_mtime_ns

    cached = _PROFILE_CACHE.get(path)
    if cached is not None and cached[0] == mtime_ns:
        return cached[1]

    data = json.loads(file_path.read_text(encoding="utf-8"))
    commands = data["commands"]
    _PROFILE_CACHE[path] = (mtime_ns, commands)
    return commands


def clear_profile_cache() -> None:
    """Clear profile cache (for tests and reloads)."""
    _PROFILE_CACHE.clear()


def resolve_profile_raw(
    path: str,
    action: str,
    hvac_mode: str | None = None,
    fan_mode: str | None = None,
    temperature: int | None = None,
) -> list[int]:
    """Resolve profile command to raw timing array."""
    commands = _load_commands(path)

    if action == "off":
        return _parse_raw(commands["off"])

    if action not in commands:
        raise ValueError(f"Action '{action}' not found in profile commands")
    if hvac_mode is None or fan_mode is None or temperature is None:
        raise ValueError(
            "For non-off actions, provide hvac_mode, fan_mode and temperature"
        )

    raw = commands[action][fan_mode][str(temperature)]
    return _parse_raw(raw)
