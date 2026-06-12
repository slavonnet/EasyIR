"""ZHA endpoint resolution for IR hubs (TS1201 defaults to endpoint 1)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DEFAULT_ENDPOINT_ID, ZHA_DOMAIN
from .supported_hubs import ieee_from_zha_device

# TS1201 IR cluster is on endpoint 1 in ZHA Quirks for Zosung/Tuya blasters.
TS1201_DEFAULT_ENDPOINT = DEFAULT_ENDPOINT_ID


def endpoint_for_zha_device(device: dr.DeviceEntry | None) -> int:
    """Return the ZHA endpoint id used for IR cluster commands on this device."""
    _ = device
    return TS1201_DEFAULT_ENDPOINT


def endpoint_for_ieee(hass: HomeAssistant, ieee: str) -> int:
    """Resolve endpoint from device registry when possible."""
    want = ieee.lower().replace(" ", "")
    reg = dr.async_get(hass)
    for dev in reg.devices.values():
        dev_ieee = ieee_from_zha_device(dev)
        if dev_ieee is None:
            continue
        if dev_ieee.lower().replace(" ", "") == want:
            return endpoint_for_zha_device(dev)
    return TS1201_DEFAULT_ENDPOINT
