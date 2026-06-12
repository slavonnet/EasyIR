"""Remote button definitions derived from IR profiles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RemoteButtonSpec:
    """One logical remote button mapped to a profile command."""

    key: str
    label: str
    action: str
    hvac_mode: str | None = None
    fan_mode: str | None = None
    temperature: int | None = None


def _load_profile(profile_path: str) -> dict[str, Any]:
    with Path(profile_path).open(encoding="utf-8") as handle:
        return json.load(handle)


def list_remote_button_specs(profile_path: str) -> list[RemoteButtonSpec]:
    """Build button specs from a profile JSON (top-level actions + off)."""
    profile = _load_profile(profile_path)
    commands = profile.get("commands")
    if not isinstance(commands, dict):
        return []

    specs: list[RemoteButtonSpec] = []
    if "off" in commands:
        specs.append(
            RemoteButtonSpec(key="off", label="Power off", action="off")
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
        label = f"{action} {fan_key}" + (f" {temp_key}°C" if temp_key and temp_key != "default" else "")
        specs.append(
            RemoteButtonSpec(
                key=f"{action}_{fan_key}_{temp_key or 'default'}",
                label=label,
                action=action,
                hvac_mode=action,
                fan_mode=str(fan_key),
                temperature=int(temp_key) if temp_key and str(temp_key).isdigit() else None,
            )
        )
    return specs
