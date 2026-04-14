"""Built-in IR profiles shipped with EasyIR."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROFILE_CUSTOM = "__custom__"

_PACKAGE_DIR = Path(__file__).resolve().parent
_PROFILES_DIR = _PACKAGE_DIR / "profiles"
_REGISTRY_FILE = _PROFILES_DIR / "registry.json"
_CLIMATE_DIR = _PROFILES_DIR / "climate"
_CLIMATE_INDEX = _PROFILES_DIR / "climate_index.json"


def profiles_dir() -> Path:
    """Directory containing bundled profile JSON files."""
    return _PROFILES_DIR


def load_registry() -> list[dict[str, Any]]:
    """Load manual registry entries (demo, overrides)."""
    if not _REGISTRY_FILE.is_file():
        return []
    data = json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
    return list(data.get("profiles", []))


def _load_climate_index() -> dict[str, str]:
    if not _CLIMATE_INDEX.is_file():
        return {}
    data = json.loads(_CLIMATE_INDEX.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}
    return {}


def _climate_json_sort_key(path: Path) -> tuple[int, str]:
    stem = path.stem
    if stem.isdigit():
        return (int(stem), stem)
    return (10**9, stem)


def select_selector_options() -> list[dict[str, str]]:
    """Options for UI: manual registry + bulk climate library + custom path."""
    options: list[dict[str, str]] = []

    for item in load_registry():
        pid = str(item.get("id", "")).strip()
        title = str(item.get("title", pid)).strip()
        fname = str(item.get("file", "")).strip()
        if not pid or not fname:
            continue
        path = _PROFILES_DIR / fname
        if not path.is_file():
            continue
        options.append({"value": pid, "label": title})

    index = _load_climate_index()
    if _CLIMATE_DIR.is_dir():
        for path in sorted(_CLIMATE_DIR.glob("*.json"), key=_climate_json_sort_key):
            rel = f"climate/{path.name}"
            stem = path.stem
            label = index.get(stem, f"Climate code {stem}")
            options.append({"value": rel, "label": label})

    options.append(
        {
            "value": PROFILE_CUSTOM,
            "label": "Custom path (advanced)",
        }
    )
    return options


def resolve_stored_profile_path(profile_choice: str, custom_path: str | None) -> str:
    """Return absolute filesystem path to profile JSON."""
    if profile_choice == PROFILE_CUSTOM:
        path = (custom_path or "").strip()
        if not path:
            msg = "Custom profile path is required when 'Custom path' is selected"
            raise ValueError(msg)
        return path

    if "/" in profile_choice or profile_choice.endswith(".json"):
        candidate = _PROFILES_DIR / profile_choice
        if candidate.is_file():
            return str(candidate.resolve())

    for item in load_registry():
        if str(item.get("id", "")).strip() != profile_choice:
            continue
        fname = str(item.get("file", "")).strip()
        if not fname:
            break
        full = _PROFILES_DIR / fname
        if full.is_file():
            return str(full.resolve())
        break

    msg = f"Unknown bundled profile: {profile_choice}"
    raise ValueError(msg)
