"""Device registry helpers for IR hubs and virtual remotes."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_AREA_ID, CONF_IEEE, DOMAIN
from .hub_registry import HubRef, RemoteRef, iter_hub_refs, iter_remote_refs, remote_display_name

HUB_DEVICE_PREFIX = "hub_"
REMOTE_DEVICE_PREFIX = "remote_"


def hub_device_identifier(subentry_id: str) -> tuple[str, str]:
    return (DOMAIN, f"{HUB_DEVICE_PREFIX}{subentry_id}")


def remote_device_identifier(subentry_id: str) -> tuple[str, str]:
    return (DOMAIN, f"{REMOTE_DEVICE_PREFIX}{subentry_id}")


def _normalize_ieee(value: str) -> str:
    return value.lower().replace(" ", "")


async def async_setup_hub_device(
    hass: HomeAssistant, entry: ConfigEntry, hub: HubRef
) -> None:
    """Register IR hub as top-level EasyIR device under the parent entry."""
    ieee = str(hub.data.get(CONF_IEEE, "")).strip()
    if not ieee:
        return
    reg = dr.async_get(hass)
    connections: set[tuple[str, str]] = set()
    connections.add((dr.CONNECTION_ZIGBEE, _normalize_ieee(ieee)))
    area_id = str(hub.data.get(CONF_AREA_ID, "")).strip() or None
    reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={hub_device_identifier(hub.subentry_id)},
        connections=connections,
        name=hub.title or f"IR Hub {ieee}",
        manufacturer="EasyIR",
        model="IR Hub",
        area_id=area_id,
    )


async def async_setup_remote_device(
    hass: HomeAssistant, entry: ConfigEntry, remote: RemoteRef, hub: HubRef | None
) -> None:
    """Register virtual remote under its IR hub."""
    if hub is None:
        return
    reg = dr.async_get(hass)
    reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={remote_device_identifier(remote.subentry_id)},
        name=remote_display_name(remote),
        manufacturer="EasyIR",
        model="Virtual IR Remote",
        via_device=hub_device_identifier(hub.subentry_id),
    )


async def async_setup_devices_for_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register all hub and remote devices for the parent config entry."""
    for hub in iter_hub_refs(hass, entry):
        await async_setup_hub_device(hass, entry, hub)
    for remote in iter_remote_refs(hass, entry):
        from .hub_registry import primary_hub_ref

        hub = primary_hub_ref(hass, remote)
        await async_setup_remote_device(hass, entry, remote, hub)
