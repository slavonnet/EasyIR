"""Suggest unconfigured IR hubs when EasyIR is installed."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, FLOW_SOURCE_ADD_HUB
from .hub_registry import configured_hub_ieees
from .supported_hubs import iter_zha_ts1201_devices, ieee_from_zha_device

_LOGGER = logging.getLogger(__name__)
_DISCOVERY_SCAN_DONE = "_hub_discovery_scan_done"


def _ieee_for_device(device) -> str | None:
    return ieee_from_zha_device(device)


@callback
def async_schedule_hub_discovery(hass: HomeAssistant) -> None:
    """Offer discovered TS1201 hubs via add-hub flow (once per HA session)."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(_DISCOVERY_SCAN_DONE):
        return
    root[_DISCOVERY_SCAN_DONE] = True
    hass.async_create_task(_async_discover_hubs(hass))


async def _async_discover_hubs(hass: HomeAssistant) -> None:
    """Start add-hub flow for each unconfigured TS1201 (EasyIR must already be set up)."""
    if not hass.config_entries.async_entries(DOMAIN):
        return
    configured = configured_hub_ieees(hass)
    for device in iter_zha_ts1201_devices(hass):
        ieee = _ieee_for_device(device)
        if ieee is None:
            continue
        norm = ieee.lower().replace(" ", "")
        if norm in configured:
            continue
        _LOGGER.debug("Suggesting discovered IR hub ieee=%s device_id=%s", ieee, device.id)
        await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": FLOW_SOURCE_ADD_HUB},
            data={"device_id": device.id, "ieee": ieee},
        )
