"""Config entry migrations for EasyIR."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant

from .config_flow import EasyIrConfigFlow
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
    PARENT_ENTRY_UNIQUE_ID,
    SUBENTRY_TYPE_HUB,
    SUBENTRY_TYPE_REMOTE,
    TRANSPORT_TS1201_ZHA,
)
from .hub_registry import (
    entry_kind,
    hub_ids_for_remote_data,
    hub_subentry_data,
    is_hub_entry,
    is_remote_entry,
    remote_subentry_data,
)


def _split_legacy_entry_data(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    hub_data = {
        CONF_ENTRY_KIND: ENTRY_KIND_HUB,
        CONF_IEEE: data[CONF_IEEE],
        CONF_ENDPOINT_ID: int(data.get(CONF_ENDPOINT_ID, DEFAULT_ENDPOINT_ID)),
        CONF_TRANSPORT: TRANSPORT_TS1201_ZHA,
    }
    remote_data = None
    if CONF_PROFILE_PATH in data:
        remote_data = {
            CONF_ENTRY_KIND: ENTRY_KIND_REMOTE,
            CONF_PROFILE_PATH: data[CONF_PROFILE_PATH],
            CONF_IEEE: data[CONF_IEEE],
        }
    return hub_data, remote_data


def _hub_subentry_from_entry(entry: ConfigEntry) -> ConfigSubentry:
    ieee = str(entry.data[CONF_IEEE])
    return ConfigSubentry(
        data=MappingProxyType(
            hub_subentry_data(
                ieee=ieee,
                endpoint_id=int(entry.data.get(CONF_ENDPOINT_ID, DEFAULT_ENDPOINT_ID)),
            )
        ),
        subentry_id=entry.entry_id,
        subentry_type=SUBENTRY_TYPE_HUB,
        title=entry.title or f"IR Hub {ieee}",
        unique_id=ieee.lower().replace(" ", ""),
    )


def _remote_subentry_from_entry(entry: ConfigEntry) -> ConfigSubentry:
    from pathlib import Path

    hub_ids = hub_ids_for_remote_data(entry.data)
    hub_id = hub_ids[0] if hub_ids else ""
    profile_path = str(entry.data[CONF_PROFILE_PATH])
    remote_name = str(entry.data.get(CONF_REMOTE_NAME, "")).strip() or None
    slug = Path(profile_path).stem
    unique = f"{hub_id}_{slug}" if hub_id else slug
    return ConfigSubentry(
        data=MappingProxyType(
            remote_subentry_data(
                hub_subentry_id=hub_id,
                profile_path=profile_path,
                remote_name=remote_name,
            )
        ),
        subentry_id=entry.entry_id,
        subentry_type=SUBENTRY_TYPE_REMOTE,
        title=entry.title or f"Remote {slug}",
        unique_id=unique,
    )


async def _drop_legacy_entry(hass: HomeAssistant, entry_id: str) -> None:
    """Remove a legacy config entry during migration without unloading platforms."""
    store = hass.config_entries._entries  # noqa: SLF001
    store.pop(entry_id, None)


async def _consolidate_v3_entries(hass: HomeAssistant) -> bool:
    """Merge legacy hub/remote config entries into one v4 parent entry."""
    entries = list(hass.config_entries.async_entries(DOMAIN))
    if not entries:
        return True
    if any(e.version >= 4 for e in entries):
        parent = next(e for e in entries if e.version >= 4)
        for extra in entries:
            if extra.entry_id != parent.entry_id:
                await _drop_legacy_entry(hass, extra.entry_id)
        return True

    hubs = [e for e in entries if is_hub_entry(e)]
    remotes = [e for e in entries if is_remote_entry(e)]
    if not hubs:
        return False

    parent = hubs[0]
    subentries: dict[str, ConfigSubentry] = {}
    for hub in hubs:
        subentries[hub.entry_id] = _hub_subentry_from_entry(hub)
    for remote in remotes:
        subentries[remote.entry_id] = _remote_subentry_from_entry(remote)

    hass.config_entries.async_update_entry(
        parent,
        title="EasyIR",
        data={},
        version=EasyIrConfigFlow.VERSION,
        minor_version=EasyIrConfigFlow.MINOR_VERSION,
        unique_id=PARENT_ENTRY_UNIQUE_ID,
        subentries=subentries,
    )

    for extra in entries:
        if extra.entry_id != parent.entry_id:
            await _drop_legacy_entry(hass, extra.entry_id)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate stored config to the v4 parent + subentries model."""
    if entry.version > EasyIrConfigFlow.VERSION:
        return False

    data = dict(entry.data)

    if entry.version < 3:
        hub_data, remote_data = _split_legacy_entry_data(data)
        hass.config_entries.async_update_entry(
            entry,
            title=entry.title or f"IR Hub {hub_data[CONF_IEEE]}",
            data=hub_data,
            version=3,
            minor_version=1,
        )
        if remote_data is not None:
            from pathlib import Path

            slug = Path(str(remote_data[CONF_PROFILE_PATH])).stem
            unique = f"{entry.entry_id}_{slug}"
            remote_entry = ConfigEntry(
                version=3,
                minor_version=1,
                domain=DOMAIN,
                title=f"Remote {slug}",
                data={
                    CONF_ENTRY_KIND: ENTRY_KIND_REMOTE,
                    CONF_HUB_ENTRY_ID: entry.entry_id,
                    CONF_HUB_IDS: [entry.entry_id],
                    CONF_PROFILE_PATH: remote_data[CONF_PROFILE_PATH],
                },
                source=entry.source,
                options={},
                unique_id=unique,
                discovery_keys=set(),
            )
            hass.config_entries._entries[remote_entry.entry_id] = remote_entry  # noqa: SLF001

    if entry.version < 2:
        data.setdefault(CONF_ENDPOINT_ID, DEFAULT_ENDPOINT_ID)
        hass.config_entries.async_update_entry(entry, data=data, version=2)

    if entry.version < 4:
        return await _consolidate_v3_entries(hass)

    return True
