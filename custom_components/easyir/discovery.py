"""Suggest unconfigured IR hubs when EasyIR is installed."""

from __future__ import annotations

import logging

from homeassistant.config_entries import SOURCE_USER, SubentryFlowContext
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, SUBENTRY_TYPE_HUB
from .hub_registry import configured_hub_ieees, parent_entry
from .supported_hubs import iter_zha_ts1201_devices, ieee_from_zha_device

_LOGGER = logging.getLogger(__name__)
_DISCOVERY_SCAN_DONE = "_hub_discovery_scan_done"


def _ieee_for_device(device) -> str | None:
    return ieee_from_zha_device(device)


@callback
def async_schedule_hub_discovery(hass: HomeAssistant) -> None:
    """Offer discovered TS1201 hubs via add-hub subentry flow (once per HA session)."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(_DISCOVERY_SCAN_DONE):
        return
    root[_DISCOVERY_SCAN_DONE] = True
    hass.async_create_task(_async_discover_hubs(hass))


async def _async_discover_hubs(hass: HomeAssistant) -> None:
    """Start add-hub subentry flow for each unconfigured TS1201."""
    parent = parent_entry(hass)
    if parent is None:
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
        await hass.config_entries.subentries.async_init(
            (parent.entry_id, SUBENTRY_TYPE_HUB),
            context=SubentryFlowContext(
                source=SOURCE_USER,
                discovery_info={"device_id": device.id, "ieee": ieee},
            ),
        )
