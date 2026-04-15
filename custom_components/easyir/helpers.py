"""IR helpers: profile parsing + vendor format transcoding."""

from __future__ import annotations

import base64
import binascii
import json
import sys
from dataclasses import dataclass
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


def decode_tuya_base64_to_raw(payload: str) -> list[int]:
    """Decode Tuya TS1201 payload back to alternating mark/space timings."""
    data = _base64_decode_loose(payload)
    pos = 0
    bytes_flat: list[int] = []
    while pos < len(data):
        chunk_len = data[pos] + 1
        pos += 1
        if pos + chunk_len > len(data):
            raise ValueError("Invalid Tuya payload chunk length")
        bytes_flat.extend(data[pos : pos + chunk_len])
        pos += chunk_len

    if len(bytes_flat) % 2 != 0:
        raise ValueError("Invalid Tuya payload: odd number of timing bytes")

    u16: list[int] = []
    for i in range(0, len(bytes_flat), 2):
        v = bytes_flat[i] | (bytes_flat[i + 1] << 8)
        u16.append(v)

    timings: list[int] = []
    for i, val in enumerate(u16):
        timings.append(val if i % 2 == 0 else -val)
    return timings


def encode_raw_to_tuya_learn_base64(raw_timings: list[int]) -> str:
    """Encode timings into Tuya learn-code (FastLZ stream wrapped as base64)."""
    if not raw_timings:
        raise ValueError("raw_timings must not be empty for Tuya learn encoding")
    payload = bytearray()
    for timing in raw_timings:
        val = _to_u16(timing)
        payload.extend((val & 0xFF, (val >> 8) & 0xFF))
    compressed = _tuya_fastlz_compress_literal(bytes(payload))
    return base64.b64encode(compressed).decode()


def decode_tuya_learn_base64_to_raw(payload: str) -> list[int]:
    """Decode Tuya learn-code base64 (FastLZ) to alternating mark/space timings."""
    data = _base64_decode_loose(payload)
    decompressed = _tuya_fastlz_decompress(data)
    if len(decompressed) % 2 != 0:
        raise ValueError("Invalid Tuya learn payload: odd number of timing bytes")
    timings: list[int] = []
    for i in range(0, len(decompressed), 2):
        val = decompressed[i] | (decompressed[i + 1] << 8)
        timings.append(val if len(timings) % 2 == 0 else -val)
    if not _looks_like_ir_timings(timings):
        raise ValueError("Decoded Tuya learn payload does not look like IR timings")
    return timings


def encode_raw_to_broadlink_base64(raw_timings: list[int]) -> str:
    """Encode timings into Broadlink-style base64 packet."""
    # Broadlink IR timing resolution used by common Home Assistant adapters.
    payload = bytearray()
    for timing in raw_timings:
        units = max(1, min(0xFFFF, int(round(abs(int(timing)) * 269 / 8192))))
        if units <= 0xFF:
            payload.append(units)
        else:
            payload.extend((0x00, (units >> 8) & 0xFF, units & 0xFF))

    packet = bytearray((0x26, 0x00, len(payload) & 0xFF, (len(payload) >> 8) & 0xFF))
    packet.extend(payload)
    packet.extend((0x0D, 0x05))
    return base64.b64encode(bytes(packet)).decode()


def decode_broadlink_base64_to_raw(payload: str) -> list[int]:
    """Decode Broadlink-style base64 packet to alternating mark/space timings."""
    data = _base64_decode_loose(payload)
    if len(data) < 6:
        raise ValueError("Broadlink payload is too short")
    if data[0] != 0x26:
        raise ValueError("Not a Broadlink IR packet signature")

    declared_len = data[2] | (data[3] << 8)
    start = 4
    end = start + declared_len
    if end > len(data):
        raise ValueError("Broadlink payload length exceeds packet size")
    body = data[start:end]
    # Some payload variants include trailer bytes inside declared window, some
    # keep additional zero padding after trailer.
    trailer_pos = body.rfind(b"\x0d\x05")
    if trailer_pos != -1:
        body = body[:trailer_pos]
    body = body.rstrip(b"\x00")
    if not body:
        raise ValueError("Broadlink payload has empty body")

    timings: list[int] = []
    idx = 0
    while idx < len(body):
        b = body[idx]
        idx += 1
        if b == 0:
            if idx + 1 >= len(body):
                # Tolerate legacy packets with trailing 0x00 padding nibble.
                if idx >= len(body) and body[-1] == 0:
                    break
                raise ValueError("Broadlink extended timing is truncated")
            units = (body[idx] << 8) | body[idx + 1]
            idx += 2
        else:
            units = b
        microseconds = int(round(units * 8192 / 269))
        sign = 1 if len(timings) % 2 == 0 else -1
        timings.append(sign * microseconds)
    if not timings:
        raise ValueError("Broadlink payload has no timing entries")
    return timings


@dataclass(frozen=True)
class DecodedIRPayload:
    raw_timings: list[int]
    source_encoding: str


def decode_ir_payload(raw: Any, encoding: str | None = None) -> DecodedIRPayload:
    """Decode profile payload into canonical timings for known encodings."""
    normalized = (encoding or "").strip().lower().replace("-", "_")
    if normalized in {"", "auto"}:
        return decode_ir_payload_auto(raw)
    if normalized in {"raw", "json", "raw_json", "list"}:
        return DecodedIRPayload(raw_timings=_parse_raw(raw), source_encoding="raw")
    if normalized in {"tuya", "tuya_base64", "ts1201", "ts1201_base64"}:
        if not isinstance(raw, str):
            raise ValueError("Tuya payload must be a base64 string")
        return DecodedIRPayload(
            raw_timings=decode_tuya_base64_to_raw(raw),
            source_encoding="tuya_base64",
        )
    if normalized in {
        "tuya_learn",
        "tuya_learn_base64",
        "tuya_fastlz",
        "tuya_ir_learn",
    }:
        if not isinstance(raw, str):
            raise ValueError("Tuya learn payload must be a base64 string")
        return DecodedIRPayload(
            raw_timings=decode_tuya_learn_base64_to_raw(raw),
            source_encoding="tuya_learn_base64",
        )
    if normalized in {"broadlink", "broadcom", "base64", "broadlink_base64"}:
        if not isinstance(raw, str):
            raise ValueError("Broadlink payload must be a base64 string")
        return DecodedIRPayload(
            raw_timings=decode_broadlink_base64_to_raw(raw),
            source_encoding="broadlink_base64",
        )
    raise ValueError(f"Unsupported IR encoding hint: {encoding!r}")


def decode_ir_payload_auto(raw: Any) -> DecodedIRPayload:
    """Try to detect payload format and decode it to canonical timings."""
    if isinstance(raw, (list, tuple)):
        return DecodedIRPayload(raw_timings=[int(x) for x in raw], source_encoding="raw")
    if raw is None:
        raise ValueError("Command raw payload is null")
    if not isinstance(raw, str):
        raise ValueError(
            f"Command raw must be a string or list, got {type(raw).__name__}"
        )
    stripped = raw.strip()
    if not stripped:
        raise ValueError("Command raw payload is empty")

    # First, try native JSON raw list format.
    try:
        return DecodedIRPayload(raw_timings=_parse_raw(stripped), source_encoding="raw")
    except ValueError:
        pass

    # Then attempt known base64 transport/vendor formats.
    if _looks_like_broadlink_packet(stripped):
        return DecodedIRPayload(
            raw_timings=decode_broadlink_base64_to_raw(stripped),
            source_encoding="broadlink_base64",
        )

    try:
        return DecodedIRPayload(
            raw_timings=decode_tuya_base64_to_raw(stripped),
            source_encoding="tuya_base64",
        )
    except ValueError:
        pass

    try:
        return DecodedIRPayload(
            raw_timings=decode_tuya_learn_base64_to_raw(stripped),
            source_encoding="tuya_learn_base64",
        )
    except ValueError:
        pass

    # Final fallback: some Broadlink payloads omit/alter padding.
    try:
        return DecodedIRPayload(
            raw_timings=decode_broadlink_base64_to_raw(stripped),
            source_encoding="broadlink_base64",
        )
    except ValueError as err:
        raise ValueError(f"Unable to auto-detect IR payload format: {err}") from err


def transcode_ir_payload(
    raw: Any,
    *,
    target_encoding: str,
    source_encoding: str | None = None,
) -> str | list[int]:
    """Transcode payload between raw / Tuya base64 / Broadlink base64 formats."""
    decoded = decode_ir_payload(raw, encoding=source_encoding)
    target = target_encoding.strip().lower().replace("-", "_")
    if target in {"raw", "json", "raw_json", "list"}:
        return list(decoded.raw_timings)
    if target in {"tuya", "tuya_base64", "ts1201", "ts1201_base64"}:
        return encode_raw_to_tuya_base64(decoded.raw_timings)
    if target in {
        "tuya_learn",
        "tuya_learn_base64",
        "tuya_fastlz",
        "tuya_ir_learn",
    }:
        return encode_raw_to_tuya_learn_base64(decoded.raw_timings)
    if target in {"broadlink", "broadcom", "base64", "broadlink_base64"}:
        return encode_raw_to_broadlink_base64(decoded.raw_timings)
    raise ValueError(f"Unsupported target encoding: {target_encoding!r}")


def _base64_decode_loose(payload: str) -> bytes:
    stripped = "".join(payload.strip().split())
    if not stripped:
        raise ValueError("Empty base64 payload")
    try:
        return base64.b64decode(stripped, validate=True)
    except (binascii.Error, ValueError):
        # Some profile payloads have missing trailing padding.
        pad = "=" * ((4 - (len(stripped) % 4)) % 4)
        try:
            return base64.b64decode(stripped + pad, validate=False)
        except (binascii.Error, ValueError) as err:
            raise ValueError(f"Invalid base64 payload: {err}") from err


def _looks_like_broadlink_packet(payload: str) -> bool:
    try:
        data = _base64_decode_loose(payload)
    except ValueError:
        return False
    if len(data) < 6 or data[0] != 0x26:
        return False
    declared_len = data[2] | (data[3] << 8)
    return declared_len > 0 and (4 + declared_len) <= len(data)


def _looks_like_ir_timings(timings: list[int]) -> bool:
    if len(timings) < 3:
        return False
    if timings[0] <= 0:
        return False
    if len(timings) > 8192:
        return False
    for idx, val in enumerate(timings):
        if val == 0:
            return False
        if idx % 2 == 0 and val < 0:
            return False
        if idx % 2 == 1 and val > 0:
            return False
        if abs(val) > 200000:
            return False
    return True


def _tuya_fastlz_decompress(data: bytes) -> bytes:
    """Decompress Tuya learn stream (FastLZ-compatible framing)."""
    pos = 0
    out = bytearray()
    while pos < len(data):
        header = data[pos]
        pos += 1
        length_code = header >> 5
        distance_hi = header & 0x1F
        if length_code == 0:
            literal_len = distance_hi + 1
            end = pos + literal_len
            if end > len(data):
                raise ValueError("Invalid Tuya learn literal block length")
            out.extend(data[pos:end])
            pos = end
            continue

        if length_code == 7:
            if pos >= len(data):
                raise ValueError("Invalid Tuya learn backref extended length")
            length_code += data[pos]
            pos += 1
        copy_len = length_code + 2
        if pos >= len(data):
            raise ValueError("Invalid Tuya learn backref distance")
        distance = ((distance_hi << 8) | data[pos]) + 1
        pos += 1
        if distance > len(out):
            raise ValueError("Invalid Tuya learn backref beyond output window")
        start = len(out) - distance
        while copy_len > 0:
            chunk = out[start : start + copy_len]
            if not chunk:
                raise ValueError("Invalid Tuya learn empty backref chunk")
            out.extend(chunk)
            copy_len -= len(chunk)
    return bytes(out)


def _tuya_fastlz_compress_literal(data: bytes) -> bytes:
    """Literal-only FastLZ stream (valid Tuya learn payload)."""
    out = bytearray()
    for i in range(0, len(data), 32):
        chunk = data[i : i + 32]
        if not chunk:
            continue
        out.append(len(chunk) - 1)
        out.extend(chunk)
    return bytes(out)


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


def _decode_profile_command_payload(raw: Any, commands_encoding: str | None) -> list[int]:
    """Decode profile command payload using encoding hint with auto fallback."""
    hint = (commands_encoding or "").strip()
    if not hint:
        return decode_ir_payload_auto(raw).raw_timings
    try:
        return decode_ir_payload(raw, encoding=hint).raw_timings
    except ValueError:
        # Some legacy profiles have incorrect commandsEncoding metadata.
        return decode_ir_payload_auto(raw).raw_timings


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
    commands_encoding = str(doc.get("commandsEncoding", "raw"))
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
        return _decode_profile_command_payload(commands["off"], commands_encoding)

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
    return _decode_profile_command_payload(raw, commands_encoding)
