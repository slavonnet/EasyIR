"""Hub and remote helpers for EasyIR (single parent entry + subentries)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENDPOINT_ID,
    CONF_ENTRY_KIND,
    CONF_HUB_ENTRY_ID,
    CONF_HUB_IDS,
    CONF_HUB_SUBENTRY_ID,
    CONF_IEEE,
    CONF_PROFILE_PATH,
    CONF_REMOTE_NAME,
    CONF_TRANSPORT,
    DEFAULT_ENDPOINT_ID,
    DOMAIN,
    ENTRY_KIND_HUB,
    ENTRY_KIND_REMOTE,
    SUBENTRY_TYPE_HUB,
    SUBENTRY_TYPE_REMOTE,
    TRANSPORT_TS1201_ZHA,
)


@dataclass(frozen=True, slots=True)
class HubRef:
    """Resolved IR hub (v4 subentry or legacy v3 config entry)."""

    subentry_id: str
    parent_entry: ConfigEntry
    subentry: ConfigSubentry | None
    title: str
    data: Mapping[str, Any]

    @property
    def entry_id(self) -> str:
        """Legacy alias used by services and entity attributes."""
        return self.subentry_id

    @property
    def hub_id(self) -> str:
        return self.subentry_id


@dataclass(frozen=True, slots=True)
class RemoteRef:
    """Resolved virtual IR remote."""

    subentry_id: str
    parent_entry: ConfigEntry
    subentry: ConfigSubentry | None
    title: str
    data: Mapping[str, Any]

    @property
    def entry_id(self) -> str:
        return self.subentry_id


def _uses_subentries(entry: ConfigEntry) -> bool:
    version = getattr(entry, "version", 0)
    try:
        return int(version) >= 4
    except (TypeError, ValueError):
        return False


def parent_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the single EasyIR parent config entry."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    for entry in entries:
        if _uses_subentries(entry):
            return entry
    return entries[0]


def entry_kind(entry: ConfigEntry) -> str:
    """Return hub or remote for legacy entries; parent entries are neither."""
    kind = str(entry.data.get(CONF_ENTRY_KIND, "")).strip().lower()
    if kind in (ENTRY_KIND_HUB, ENTRY_KIND_REMOTE):
        return kind
    if CONF_PROFILE_PATH in entry.data and CONF_IEEE in entry.data:
        return ENTRY_KIND_REMOTE
    if CONF_IEEE in entry.data:
        return ENTRY_KIND_HUB
    return ENTRY_KIND_REMOTE


def is_hub_entry(entry: ConfigEntry) -> bool:
    if _uses_subentries(entry):
        return False
    return entry_kind(entry) == ENTRY_KIND_HUB


def is_remote_entry(entry: ConfigEntry) -> bool:
    if _uses_subentries(entry):
        return False
    return entry_kind(entry) == ENTRY_KIND_REMOTE


def _hub_ref_from_subentry(parent: ConfigEntry, subentry: ConfigSubentry) -> HubRef:
    return HubRef(
        subentry_id=subentry.subentry_id,
        parent_entry=parent,
        subentry=subentry,
        title=subentry.title,
        data=subentry.data,
    )


def _remote_ref_from_subentry(parent: ConfigEntry, subentry: ConfigSubentry) -> RemoteRef:
    return RemoteRef(
        subentry_id=subentry.subentry_id,
        parent_entry=parent,
        subentry=subentry,
        title=subentry.title,
        data=subentry.data,
    )


def _legacy_hub_ref(entry: ConfigEntry) -> HubRef:
    return HubRef(
        subentry_id=entry.entry_id,
        parent_entry=entry,
        subentry=None,
        title=entry.title,
        data=entry.data,
    )


def _legacy_remote_ref(entry: ConfigEntry) -> RemoteRef:
    return RemoteRef(
        subentry_id=entry.entry_id,
        parent_entry=entry,
        subentry=None,
        title=entry.title,
        data=entry.data,
    )


def iter_hub_refs(hass: HomeAssistant, entry: ConfigEntry | None = None) -> list[HubRef]:
    """List configured IR hubs."""
    parent = entry or parent_entry(hass)
    if parent is None:
        return []
    if _uses_subentries(parent):
        hubs = [
            _hub_ref_from_subentry(parent, sub)
            for sub in parent.subentries.values()
            if sub.subentry_type == SUBENTRY_TYPE_HUB
        ]
    else:
        hubs = [_legacy_hub_ref(parent)] if is_hub_entry(parent) else []
        for other in hass.config_entries.async_entries(DOMAIN):
            if other.entry_id != parent.entry_id and is_hub_entry(other):
                hubs.append(_legacy_hub_ref(other))
    hubs.sort(key=lambda h: (h.title or "", h.subentry_id))
    return hubs


def iter_remote_refs(hass: HomeAssistant, entry: ConfigEntry | None = None) -> list[RemoteRef]:
    """List configured virtual remotes."""
    parent = entry or parent_entry(hass)
    if parent is None:
        return []
    if _uses_subentries(parent):
        remotes = [
            _remote_ref_from_subentry(parent, sub)
            for sub in parent.subentries.values()
            if sub.subentry_type == SUBENTRY_TYPE_REMOTE
        ]
    else:
        remotes = []
        for other in hass.config_entries.async_entries(DOMAIN):
            if is_remote_entry(other):
                remotes.append(_legacy_remote_ref(other))
    remotes.sort(key=lambda r: (r.title or "", r.subentry_id))
    return remotes


def iter_hub_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """Legacy helper: hub config entries (empty on v4 parent model)."""
    return [e for e in hass.config_entries.async_entries(DOMAIN) if is_hub_entry(e)]


def iter_remote_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """Legacy helper: remote config entries (empty on v4 parent model)."""
    return [e for e in hass.config_entries.async_entries(DOMAIN) if is_remote_entry(e)]


def _normalize_ieee(value: str) -> str:
    return value.lower().replace(" ", "")


def hub_ref_by_id(hass: HomeAssistant, hub_id: str) -> HubRef | None:
    target = str(hub_id).strip()
    if not target:
        return None
    for hub in iter_hub_refs(hass):
        if hub.subentry_id == target:
            return hub
    return None


def hub_entry_by_id(hass: HomeAssistant, hub_entry_id: str) -> ConfigEntry | None:
    """Legacy lookup by hub id (subentry id on v4)."""
    hub = hub_ref_by_id(hass, hub_entry_id)
    if hub is None:
        return None
    if hub.subentry is None:
        return hub.parent_entry
    return hub.parent_entry


def hub_ref_for_ieee(hass: HomeAssistant, ieee: str) -> HubRef | None:
    want = _normalize_ieee(ieee)
    for hub in iter_hub_refs(hass):
        current = _normalize_ieee(str(hub.data.get(CONF_IEEE, "")))
        if current == want:
            return hub
    return None


def hub_entry_for_ieee(hass: HomeAssistant, ieee: str) -> ConfigEntry | None:
    hub = hub_ref_for_ieee(hass, ieee)
    return hub.parent_entry if hub else None


def hub_ids_for_remote_data(data: Mapping[str, Any]) -> list[str]:
    """Return hub subentry ids targeted by a remote."""
    raw_ids = data.get(CONF_HUB_IDS)
    if isinstance(raw_ids, (list, tuple)):
        ids = [str(x).strip() for x in raw_ids if str(x).strip()]
        if ids:
            return ids
    for key in (CONF_HUB_SUBENTRY_ID, CONF_HUB_ENTRY_ID):
        hub_id = str(data.get(key, "")).strip()
        if hub_id:
            return [hub_id]
    ieee = str(data.get(CONF_IEEE, "")).strip()
    if ieee:
        return [ieee]
    return []


def hub_ids_for_remote(remote: RemoteRef | ConfigEntry) -> list[str]:
    if isinstance(remote, RemoteRef):
        return hub_ids_for_remote_data(remote.data)
    return hub_ids_for_remote_data(remote.data)


def hub_refs_for_remote(hass: HomeAssistant, remote: RemoteRef | ConfigEntry) -> list[HubRef]:
    """Resolve hub refs for a remote."""
    data = remote.data if isinstance(remote, RemoteRef) else remote.data
    hubs: list[HubRef] = []
    for hub_ref in hub_ids_for_remote_data(data):
        hub = hub_ref_by_id(hass, hub_ref)
        if hub is None:
            hub = hub_ref_for_ieee(hass, hub_ref)
        if hub is not None and hub not in hubs:
            hubs.append(hub)
    return hubs


def hub_entries_for_remote(hass: HomeAssistant, remote_entry: ConfigEntry) -> list[ConfigEntry]:
    """Legacy helper returning parent entries for linked hubs."""
    remote = _legacy_remote_ref(remote_entry)
    return [h.parent_entry for h in hub_refs_for_remote(hass, remote)]


def primary_hub_ref(hass: HomeAssistant, remote: RemoteRef | ConfigEntry) -> HubRef | None:
    hubs = hub_refs_for_remote(hass, remote)
    return hubs[0] if hubs else None


def primary_hub_entry(hass: HomeAssistant, remote_entry: ConfigEntry) -> ConfigEntry | None:
    if isinstance(remote_entry, ConfigEntry) and _uses_subentries(remote_entry):
        remotes = iter_remote_refs(hass, remote_entry)
        if len(remotes) == 1:
            return primary_hub_ref(hass, remotes[0]).parent_entry if primary_hub_ref(hass, remotes[0]) else None
        return remote_entry
    remote = (
        remote_entry
        if isinstance(remote_entry, RemoteRef)
        else _legacy_remote_ref(remote_entry)
    )
    hub = primary_hub_ref(hass, remote)
    return hub.parent_entry if hub else None


def hub_transport_data(hub: HubRef | ConfigEntry) -> dict[str, Any]:
    """Transport fields for a hub."""
    data = hub.data if isinstance(hub, HubRef) else hub.data
    return {
        CONF_IEEE: str(data[CONF_IEEE]),
        CONF_ENDPOINT_ID: int(data.get(CONF_ENDPOINT_ID, DEFAULT_ENDPOINT_ID)),
        CONF_TRANSPORT: str(data.get(CONF_TRANSPORT, TRANSPORT_TS1201_ZHA)),
    }


def remote_display_name(remote: RemoteRef | ConfigEntry) -> str:
    data = remote.data if isinstance(remote, RemoteRef) else remote.data
    title = remote.title if isinstance(remote, RemoteRef) else remote.title
    name = str(data.get(CONF_REMOTE_NAME, "")).strip()
    if name:
        return name
    if CONF_PROFILE_PATH in data:
        return str(PathLikeProfileName(str(data[CONF_PROFILE_PATH])))
    return title or "IR Remote"


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
    for hub in iter_hub_refs(hass):
        ieee = str(hub.data.get(CONF_IEEE, "")).strip()
        if ieee:
            out.add(_normalize_ieee(ieee))
    return out


def hub_subentry_data(
    *,
    ieee: str,
    endpoint_id: int,
    area_id: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        CONF_IEEE: ieee,
        CONF_ENDPOINT_ID: endpoint_id,
        CONF_TRANSPORT: TRANSPORT_TS1201_ZHA,
    }
    if area_id:
        data[CONF_AREA_ID] = area_id
    return data


def remote_subentry_data(
    *,
    hub_subentry_id: str,
    profile_path: str,
    remote_name: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        CONF_HUB_SUBENTRY_ID: hub_subentry_id,
        CONF_HUB_ENTRY_ID: hub_subentry_id,
        CONF_HUB_IDS: [hub_subentry_id],
        CONF_PROFILE_PATH: profile_path,
    }
    if remote_name:
        data[CONF_REMOTE_NAME] = remote_name
    return data
