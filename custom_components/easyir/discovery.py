"""Suggest unconfigured IR hubs when EasyIR is installed."""

from __future__ import annotations

import logging

from homeassistant.config_entries import SOURCE_USER, SubentryFlowContext
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, SUBENTRY_TYPE_HUB
from .hub_registry import configured_hub_ieees, parent_entry
from .supported_hubs import iter_zha_ts1201_devices, ieee_from_zha_device

_LOGGER = logging.getLogger(__name__)
_DISCOVERY_LISTENER_UNSUB = "_hub_discovery_listener_unsub"
_DISCOVERY_SCAN_TASK = "_hub_discovery_scan_task"
_DISCOVERY_PROMPTED_IEEE = "_hub_discovery_prompted_ieee"


def _ieee_for_device(device) -> str | None:
    return ieee_from_zha_device(device)


@callback
def async_schedule_hub_discovery(hass: HomeAssistant) -> None:
    """Watch for discoverable TS1201 hubs and suggest add-hub flows."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get(_DISCOVERY_LISTENER_UNSUB):
        async_request_hub_discovery_scan(hass)
        return

    @callback
    def _handle_device_registry_updated(event) -> None:
        data = event.data or {}
        action = str(data.get("action", ""))
        if action not in {"create", "update"}:
            return
        async_request_hub_discovery_scan(hass)

    unsub = hass.bus.async_listen(
        dr.EVENT_DEVICE_REGISTRY_UPDATED, _handle_device_registry_updated
    )
    root[_DISCOVERY_LISTENER_UNSUB] = unsub
    async_request_hub_discovery_scan(hass)


@callback
def async_request_hub_discovery_scan(hass: HomeAssistant) -> None:
    """Request a coalesced async discovery scan."""
    root = hass.data.setdefault(DOMAIN, {})
    task = root.get(_DISCOVERY_SCAN_TASK)
    if task and not task.done():
        return
    root[_DISCOVERY_SCAN_TASK] = hass.async_create_task(_async_discover_hubs(hass))


async def _async_discover_hubs(hass: HomeAssistant) -> None:
    """Start add-hub subentry flow for each newly discoverable TS1201."""
    root = hass.data.setdefault(DOMAIN, {})
    parent = parent_entry(hass)
    if parent is None:
        return

    prompted_ieee: set[str] = root.setdefault(_DISCOVERY_PROMPTED_IEEE, set())
    configured = configured_hub_ieees(hass)
    prompted_ieee.difference_update(configured)

    available_ieee: set[str] = set()
    for device in iter_zha_ts1201_devices(hass):
        ieee = _ieee_for_device(device)
        if ieee is None:
            continue
        norm = ieee.lower().replace(" ", "")
        available_ieee.add(norm)
        if norm in configured:
            continue
        if norm in prompted_ieee:
            continue
        _LOGGER.debug("Suggesting discovered IR hub ieee=%s device_id=%s", ieee, device.id)
        prompted_ieee.add(norm)
        await hass.config_entries.subentries.async_init(
            (parent.entry_id, SUBENTRY_TYPE_HUB),
            context=SubentryFlowContext(
                source=SOURCE_USER,
                discovery_info={"device_id": device.id, "ieee": ieee},
            ),
        )

    # Forget prompts for devices removed from registry so they can be suggested again.
    prompted_ieee.intersection_update(available_ieee | configured)
