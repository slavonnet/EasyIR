"""Bind bundled profiles to pilot capability constraints (climate entity path)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import load_lg_p12rk_capabilities


def _read_profile_meta(path: str) -> dict[str, Any] | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data


def is_lg_p12rk_profile(path: str) -> bool:
    """Return True when profile metadata matches LG P12RK pilot binding."""
    data = _read_profile_meta(path)
    if not data:
        return False
    if str(data.get("manufacturer", "")).strip().upper() != "LG":
        return False
    models = data.get("supportedModels") or []
    if not isinstance(models, list):
        return False
    for m in models:
        if isinstance(m, str) and "P12RK" in m.upper():
            return True
    return False


def climate_capability_view(path: str) -> dict[str, Any]:
    """Capability-driven view for climate setup (pilot vs default MVP)."""
    if not is_lg_p12rk_profile(path):
        return {"protocol": "legacy_profile", "pilot": False}

    caps = load_lg_p12rk_capabilities()
    opt = caps.get("optional_features") or {}
    ion = (opt.get("ionizer") or {}) if isinstance(opt, dict) else {}
    ion_supported = bool(ion.get("supported")) if isinstance(ion, dict) else False

    return {
        "protocol": caps.get("model_id", "lg_p12rk"),
        "pilot": True,
        "hvac_modes": list(caps.get("hvac_modes", [])),
        "fan_modes": list(caps.get("fan_modes", [])),
        "temperature_c": dict(caps.get("temperature_c", {})),
        "ionizer_supported": ion_supported,
    }
