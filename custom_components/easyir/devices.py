"""Device registry helpers for IR hubs and virtual remotes."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_IEEE, DOMAIN, ZHA_DOMAIN
from .hub_registry import entry_kind, is_hub_entry, is_remote_entry, primary_hub_entry, remote_display_name

HUB_DEVICE_PREFIX = "hub_"
REMOTE_DEVICE_PREFIX = "remote_"


def hub_device_identifier(entry_id: str) -> tuple[str, str]:
    return (DOMAIN, f"{HUB_DEVICE_PREFIX}{entry_id}")


def remote_device_identifier(entry_id: str) -> tuple[str, str]:
    return (DOMAIN, f"{REMOTE_DEVICE_PREFIX}{entry_id}")


def _normalize_ieee(value: str) -> str:
    return value.lower().replace(" ", "")


async def async_setup_hub_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register IR hub in device registry (child of ZHA TS1201)."""
    if not is_hub_entry(entry):
        return
    ieee = str(entry.data.get(CONF_IEEE, "")).strip()
    if not ieee:
        return
    reg = dr.async_get(hass)
    reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={hub_device_identifier(entry.entry_id)},
        name=entry.title or f"IR Hub {ieee}",
        manufacturer="EasyIR",
        model="IR Hub",
        via_device=(ZHA_DOMAIN, _normalize_ieee(ieee)),
    )


async def async_setup_remote_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register virtual remote under its IR hub in device registry."""
    if not is_remote_entry(entry):
        return
    hub = primary_hub_entry(hass, entry)
    via_device = hub_device_identifier(hub.entry_id) if hub is not None else None
    reg = dr.async_get(hass)
    reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={remote_device_identifier(entry.entry_id)},
        name=remote_display_name(entry),
        manufacturer="EasyIR",
        model="Virtual IR Remote",
        via_device=via_device,
    )
