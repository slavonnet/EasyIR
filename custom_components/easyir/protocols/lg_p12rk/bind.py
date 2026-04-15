"""Bind bundled profiles to pilot capability constraints (climate entity path)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .engine import load_lg_p12rk_capabilities

_OPTIONAL_LG_FLAGS = frozenset({"ionizer", "energy_saving", "auto_clean"})


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


def _optional_supported(caps: dict[str, Any], key: str) -> bool:
    opt = caps.get("optional_features") or {}
    if not isinstance(opt, dict):
        return False
    block = opt.get(key)
    if not isinstance(block, dict):
        return False
    return bool(block.get("supported"))


def climate_capability_view(path: str) -> dict[str, Any]:
    """Capability-driven view for climate setup (pilot vs default MVP)."""
    if not is_lg_p12rk_profile(path):
        return {"protocol": "legacy_profile", "pilot": False}

    caps = load_lg_p12rk_capabilities()
    data = _read_profile_meta(path) or {}
    profile_flags = {
        str(x).strip().lower() for x in (data.get("easyir_feature_flags") or [])
    }
    opt_in = profile_flags & _OPTIONAL_LG_FLAGS
    if not opt_in:
        # Profile did not list optional LG flags: treat as full pilot model capability
        # (bundled profiles without flags still get the capability matrix defaults).
        ion_supported = _optional_supported(caps, "ionizer")
        energy_supported = _optional_supported(caps, "energy_saving")
        auto_clean_supported = _optional_supported(caps, "auto_clean")
    else:
        ion_supported = "ionizer" in opt_in and _optional_supported(caps, "ionizer")
        energy_supported = "energy_saving" in opt_in and _optional_supported(
            caps, "energy_saving"
        )
        auto_clean_supported = "auto_clean" in opt_in and _optional_supported(
            caps, "auto_clean"
        )

    profile_proto = str(data.get("easyir_protocol", "")).strip()
    protocol_id = profile_proto or str(caps.get("model_id", "lg_p12rk"))

    return {
        "protocol": protocol_id,
        "pilot": True,
        "hvac_modes": list(caps.get("hvac_modes", [])),
        "fan_modes": list(caps.get("fan_modes", [])),
        "temperature_c": dict(caps.get("temperature_c", {})),
        "ionizer_supported": ion_supported,
        "energy_saving_supported": energy_supported,
        "auto_clean_supported": auto_clean_supported,
        "easyir_feature_flags": list(data.get("easyir_feature_flags") or []),
    }
