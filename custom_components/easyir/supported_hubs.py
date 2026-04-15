"""Supported hub discovery helpers (ZHA TS1201 and future transports)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, ZHA_DOMAIN


def _is_ts1201_model(device: dr.DeviceEntry) -> bool:
    """Heuristic: ZHA exposes Tuya IR blasters with model name TS1201."""
    model = (device.model or "").strip()
    model_id = (getattr(device, "model_id", None) or "").strip()
    return model == "TS1201" or model_id == "TS1201"


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
    configured: set[str] = set()
    for entry in hass.config_entries.async_entries(DOMAIN):
        ieee = str(entry.data.get("ieee", "")).lower().replace(" ", "")
        if ieee:
            configured.add(ieee)

    choices: list[tuple[str, str]] = []
    for dev in iter_zha_ts1201_devices(hass):
        ieee = None
        for dom, value in dev.identifiers:
            if dom == ZHA_DOMAIN:
                ieee = str(value).lower().replace(" ", "")
                break
        if ieee is None:
            for conn_kind, value in dev.connections:
                if conn_kind == "zigbee":
                    ieee = str(value).lower().replace(" ", "")
                    break
        if ieee is None or ieee in configured:
            continue
        label = dev.name_by_user or dev.name or ieee
        choices.append((dev.id, f"{label} ({ieee})"))
    return choices
