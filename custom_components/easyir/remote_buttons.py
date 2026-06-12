"""Remote button definitions derived from IR profiles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class ButtonCommandKind(str, Enum):
    """How the button maps to IR encoding on send."""

    STATE_FRAME = "state_frame"
    """Grouped HVAC frame (mode + fan + temperature) or power-off."""

    FEATURE_COMMAND = "feature_command"
    """Separate protocol command word (ionizer, energy saving, …)."""


@dataclass(frozen=True, slots=True)
class RemoteButtonSpec:
    """One logical remote button mapped to a profile command."""

    key: str
    label: str
    action: str
    kind: ButtonCommandKind
    hvac_mode: str | None = None
    fan_mode: str | None = None
    temperature: int | None = None
    feature_key: str | None = None


# LG universal: extras are discrete command16 words, not packed in the 28-bit state frame.
_LG_FEATURE_BUTTONS: dict[str, list[tuple[str, str, str]]] = {
    "ionizer": [
        ("ionizer_on", "Ionizer on", "ionizer"),
        ("ionizer_off", "Ionizer off", "ionizer"),
    ],
    "energy_saving": [
        ("energy_saving_on", "Energy saving on", "energy_saving"),
        ("energy_saving_off", "Energy saving off", "energy_saving"),
    ],
    "auto_clean": [
        ("auto_clean_on", "Auto clean on", "auto_clean"),
        ("auto_clean_off", "Auto clean off", "auto_clean"),
    ],
    "jet": [("jet_on", "Jet mode", "jet")],
    "swing": [
        ("swing_on", "Swing on", "swing"),
        ("swing_off", "Swing off", "swing"),
    ],
    "wall_swing": [
        ("wall_swing_on", "Wall swing on", "wall_swing"),
        ("wall_swing_off", "Wall swing off", "wall_swing"),
    ],
    "light": [("light", "Light toggle", "light")],
}


def _load_profile(profile_path: str) -> dict[str, Any]:
    with Path(profile_path).open(encoding="utf-8") as handle:
        return json.load(handle)


def _profile_uses_lg_universal(profile: dict[str, Any]) -> bool:
    try:
        from .protocols.lg_universal.engine import profile_uses_lg_universal_encoder

        return profile_uses_lg_universal_encoder(profile)
    except ImportError:
        proto = str(profile.get("easyir_protocol", "")).strip().lower()
        enc = str(profile.get("easyir_encoding", "raw")).strip().lower()
        return proto in ("lg_universal_v1", "lg_universal") and enc == "lg28"


def _lg_feature_button_specs(profile: dict[str, Any]) -> list[RemoteButtonSpec]:
    """Discrete LG command-word buttons gated by profile easyir_feature_flags."""
    flags = {
        str(x).strip().lower() for x in (profile.get("easyir_feature_flags") or [])
    }
    specs: list[RemoteButtonSpec] = []
    for flag_name, entries in _LG_FEATURE_BUTTONS.items():
        if flag_name not in flags:
            continue
        for action, label, feature_key in entries:
            specs.append(
                RemoteButtonSpec(
                    key=action,
                    label=label,
                    action=action,
                    kind=ButtonCommandKind.FEATURE_COMMAND,
                    feature_key=feature_key,
                )
            )
    return specs


def _legacy_state_frame_specs(commands: dict[str, Any]) -> list[RemoteButtonSpec]:
    """Buttons from legacy commands matrix (each sends one full state/raw payload)."""
    specs: list[RemoteButtonSpec] = []
    if "off" in commands:
        specs.append(
            RemoteButtonSpec(
                key="off",
                label="Power off",
                action="off",
                kind=ButtonCommandKind.STATE_FRAME,
            )
        )

    for action in ("cool", "dry", "heat", "fan_only", "auto"):
        node = commands.get(action)
        if node is None:
            continue
        if isinstance(node, str):
            specs.append(
                RemoteButtonSpec(
                    key=action,
                    label=action.replace("_", " ").title(),
                    action=action,
                    kind=ButtonCommandKind.STATE_FRAME,
                    hvac_mode=action,
                )
            )
            continue
        if not isinstance(node, dict):
            continue
        fan_key = next(iter(node.keys()), None)
        if fan_key is None:
            continue
        temp_node = node.get(fan_key)
        temp_key = None
        if isinstance(temp_node, dict):
            temp_key = next(iter(temp_node.keys()), None)
        elif isinstance(temp_node, str):
            temp_key = "default"
        label = f"{action} {fan_key}" + (
            f" {temp_key}°C" if temp_key and temp_key != "default" else ""
        )
        specs.append(
            RemoteButtonSpec(
                key=f"{action}_{fan_key}_{temp_key or 'default'}",
                label=label,
                action=action,
                kind=ButtonCommandKind.STATE_FRAME,
                hvac_mode=action,
                fan_mode=str(fan_key),
                temperature=int(temp_key) if temp_key and str(temp_key).isdigit() else None,
            )
        )
    return specs


def list_remote_button_specs(profile_path: str) -> list[RemoteButtonSpec]:
    """Build button specs: grouped HVAC state frames vs separate feature commands."""
    profile = _load_profile(profile_path)
    commands = profile.get("commands")
    if not isinstance(commands, dict):
        return []

    if _profile_uses_lg_universal(profile):
        specs: list[RemoteButtonSpec] = []
        if "off" in commands or "power_off" in (
            profile.get("easyir_feature_flags") or []
        ):
            specs.append(
                RemoteButtonSpec(
                    key="off",
                    # LG off command is effectively a power toggle on many units.
                    label="Power toggle",
                    action="off",
                    kind=ButtonCommandKind.STATE_FRAME,
                )
            )
        specs.extend(_lg_feature_button_specs(profile))
        return specs

    return _legacy_state_frame_specs(commands)
