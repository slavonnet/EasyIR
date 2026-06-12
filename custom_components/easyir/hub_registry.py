"""Hub and remote config-entry helpers (hub-centric EasyIR model)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENDPOINT_ID,
    CONF_ENTRY_KIND,
    CONF_HUB_ENTRY_ID,
    CONF_HUB_IDS,
    CONF_IEEE,
    CONF_PROFILE_PATH,
    CONF_REMOTE_NAME,
    CONF_TRANSPORT,
    DEFAULT_ENDPOINT_ID,
    DOMAIN,
    ENTRY_KIND_HUB,
    ENTRY_KIND_REMOTE,
    TRANSPORT_TS1201_ZHA,
)


def entry_kind(entry: ConfigEntry) -> str:
    """Return hub or remote; legacy combined entries are treated as remote."""
    kind = str(entry.data.get(CONF_ENTRY_KIND, "")).strip().lower()
    if kind in (ENTRY_KIND_HUB, ENTRY_KIND_REMOTE):
        return kind
    if CONF_PROFILE_PATH in entry.data and CONF_IEEE in entry.data:
        return ENTRY_KIND_REMOTE
    if CONF_IEEE in entry.data:
        return ENTRY_KIND_HUB
    return ENTRY_KIND_REMOTE


def is_hub_entry(entry: ConfigEntry) -> bool:
    return entry_kind(entry) == ENTRY_KIND_HUB


def is_remote_entry(entry: ConfigEntry) -> bool:
    return entry_kind(entry) == ENTRY_KIND_REMOTE


def iter_hub_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN) if is_hub_entry(e)
    ]
    entries.sort(key=lambda e: (getattr(e, "title", None) or "", getattr(e, "entry_id", "")))
    return entries


def iter_remote_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN) if is_remote_entry(e)
    ]
    entries.sort(key=lambda e: (getattr(e, "title", None) or "", getattr(e, "entry_id", "")))
    return entries


def _normalize_ieee(value: str) -> str:
    return value.lower().replace(" ", "")


def hub_entry_by_id(hass: HomeAssistant, hub_entry_id: str) -> ConfigEntry | None:
    target = str(hub_entry_id).strip()
    if not target:
        return None
    for entry in iter_hub_entries(hass):
        if entry.entry_id == target:
            return entry
    return None


def hub_entry_for_ieee(hass: HomeAssistant, ieee: str) -> ConfigEntry | None:
    want = _normalize_ieee(ieee)
    for entry in iter_hub_entries(hass):
        current = _normalize_ieee(str(entry.data.get(CONF_IEEE, "")))
        if current == want:
            return entry
    return None


def hub_ids_for_remote(entry: ConfigEntry) -> list[str]:
    """Return hub config entry ids targeted by a remote entry."""
    raw_ids = entry.data.get(CONF_HUB_IDS)
    if isinstance(raw_ids, (list, tuple)):
        ids = [str(x).strip() for x in raw_ids if str(x).strip()]
        if ids:
            return ids
    hub_id = str(entry.data.get(CONF_HUB_ENTRY_ID, "")).strip()
    if hub_id:
        return [hub_id]
    ieee = str(entry.data.get(CONF_IEEE, "")).strip()
    if ieee:
        return [ieee]
    return []


def hub_entries_for_remote(hass: HomeAssistant, remote_entry: ConfigEntry) -> list[ConfigEntry]:
    """Resolve hub config entries for a remote (by hub entry id or legacy ieee)."""
    hubs: list[ConfigEntry] = []
    for hub_ref in hub_ids_for_remote(remote_entry):
        hub = hub_entry_by_id(hass, hub_ref)
        if hub is None:
            hub = hub_entry_for_ieee(hass, hub_ref)
        if hub is not None and hub not in hubs:
            hubs.append(hub)
    return hubs


def primary_hub_entry(hass: HomeAssistant, remote_entry: ConfigEntry) -> ConfigEntry | None:
    hubs = hub_entries_for_remote(hass, remote_entry)
    return hubs[0] if hubs else None


def hub_transport_data(entry: ConfigEntry) -> dict[str, Any]:
    """Transport fields for a hub entry."""
    return {
        CONF_IEEE: str(entry.data[CONF_IEEE]),
        CONF_ENDPOINT_ID: int(entry.data.get(CONF_ENDPOINT_ID, DEFAULT_ENDPOINT_ID)),
        CONF_TRANSPORT: str(entry.data.get(CONF_TRANSPORT, TRANSPORT_TS1201_ZHA)),
    }


def remote_display_name(entry: ConfigEntry) -> str:
    name = str(entry.data.get(CONF_REMOTE_NAME, "")).strip()
    if name:
        return name
    if CONF_PROFILE_PATH in entry.data:
        return PathLikeProfileName(str(entry.data[CONF_PROFILE_PATH]))
    return entry.title or "IR Remote"


class PathLikeProfileName:
    """Lazy profile basename for display."""

    __slots__ = ("_path",)

    def __init__(self, path: str) -> None:
        self._path = path

    def __str__(self) -> str:
        from pathlib import Path

        stem = Path(self._path).stem
        return stem if stem else "IR Remote"


def configured_hub_ieees(hass: HomeAssistant) -> set[str]:
    out: set[str] = set()
    for entry in iter_hub_entries(hass):
        ieee = str(entry.data.get(CONF_IEEE, "")).strip()
        if ieee:
            out.add(_normalize_ieee(ieee))
    return out
