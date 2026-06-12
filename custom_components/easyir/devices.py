"""Device registry helpers for IR hubs and virtual remotes."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_IEEE, DOMAIN
from .hub_registry import is_hub_entry, is_remote_entry, primary_hub_entry, remote_display_name

HUB_DEVICE_PREFIX = "hub_"
REMOTE_DEVICE_PREFIX = "remote_"


def hub_device_identifier(entry_id: str) -> tuple[str, str]:
    return (DOMAIN, f"{HUB_DEVICE_PREFIX}{entry_id}")


def remote_device_identifier(entry_id: str) -> tuple[str, str]:
    return (DOMAIN, f"{REMOTE_DEVICE_PREFIX}{entry_id}")


def _normalize_ieee(value: str) -> str:
    return value.lower().replace(" ", "")


async def async_setup_hub_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register IR hub as top-level EasyIR device (Zigbee link via connection only)."""
    if not is_hub_entry(entry):
        return
    ieee = str(entry.data.get(CONF_IEEE, "")).strip()
    if not ieee:
        return
    reg = dr.async_get(hass)
    connections: set[tuple[str, str]] = set()
    if ieee:
        connections.add((dr.CONNECTION_ZIGBEE, _normalize_ieee(ieee)))
    reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={hub_device_identifier(entry.entry_id)},
        connections=connections,
        name=entry.title or f"IR Hub {ieee}",
        manufacturer="EasyIR",
        model="IR Hub",
    )


async def async_setup_remote_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register virtual remote under its IR hub (single device tree under hub entry)."""
    if not is_remote_entry(entry):
        return
    hub = primary_hub_entry(hass, entry)
    if hub is None:
        return
    reg = dr.async_get(hass)
    reg.async_get_or_create(
        config_entry_id=hub.entry_id,
        identifiers={remote_device_identifier(entry.entry_id)},
        name=remote_display_name(entry),
        manufacturer="EasyIR",
        model="Virtual IR Remote",
        via_device=hub_device_identifier(hub.entry_id),
    )
