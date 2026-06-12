"""Supported hub discovery helpers (ZHA TS1201 and future transports)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import ZHA_DOMAIN
from .hub_registry import configured_hub_ieees


def _is_ts1201_model(device: dr.DeviceEntry) -> bool:
    """Heuristic: ZHA exposes Tuya IR blasters with model name TS1201."""
    model = (device.model or "").strip()
    model_id = (getattr(device, "model_id", None) or "").strip()
    return model == "TS1201" or model_id == "TS1201"


def ieee_from_zha_device(device: dr.DeviceEntry) -> str | None:
    """Extract Zigbee IEEE from a ZHA device registry entry."""
    for dom, value in device.identifiers:
        if dom == ZHA_DOMAIN:
            return str(value)
    for conn_kind, value in device.connections:
        if conn_kind == "zigbee":
            return str(value)
    return None


def iter_zha_ts1201_devices(hass: HomeAssistant) -> list[dr.DeviceEntry]:
    """Return ZHA device registry entries that look like TS1201 IR blasters."""
    reg = dr.async_get(hass)
    out: list[dr.DeviceEntry] = []
    for dev in reg.devices.values():
        if dev.disabled_by is not None:
            continue
        if not any(dom == ZHA_DOMAIN for dom, _ in dev.identifiers):
            continue
        if _is_ts1201_model(dev):
            out.append(dev)
    out.sort(key=lambda d: (d.name or "", d.id))
    return out


def list_onboarding_hub_choices(hass: HomeAssistant) -> list[tuple[str, str]]:
    """Return (device_registry_id, label) pairs for supported-but-unconfigured hubs."""
    configured = configured_hub_ieees(hass)

    choices: list[tuple[str, str]] = []
    for dev in iter_zha_ts1201_devices(hass):
        ieee_raw = ieee_from_zha_device(dev)
        if ieee_raw is None:
            continue
        ieee = ieee_raw.lower().replace(" ", "")
        if ieee in configured:
            continue
        label = dev.name_by_user or dev.name or ieee
        choices.append((dev.id, f"{label} ({ieee})"))
    return choices
