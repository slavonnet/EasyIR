"""EasyIR custom integration."""

from __future__ import annotations

from functools import partial
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .command_pool import DEFAULT_POOL_INTERVAL_S, get_service_call_pool
from .const import (
    CONF_ENDPOINT_ID,
    CONF_HUB_ID,
    CONF_IEEE,
    CONF_PROFILE_PATH,
    DEBUG_EVENT_LEARN_ONCE_HANDLER_ENTER,
    DEFAULT_ENDPOINT_ID,
    DOMAIN,
    PLATFORMS,
    SERVICE_CAPTURE_INBOUND,
    SERVICE_LEARN_CODE_LEGACY,
    SERVICE_LEARN_ONCE,
    SERVICE_READ_LEARNED,
    SERVICE_SEND_RAW,
    SERVICE_SEND_COMMAND,
    SERVICE_START_LEARN,
    SERVICE_STOP_LEARN,
    TS1201_ENDPOINT_ID,
)
from .devices import async_setup_devices_for_entry
from .discovery import async_schedule_hub_discovery
from .hub_registry import (
    hub_ref_by_id,
    hub_ref_for_ieee,
    hub_transport_data,
    iter_hub_refs,
    parent_entry,
)
from .ir_core.service_adapter import (
    encode_profile_command_for_zha_ts1201,
    encode_raw_timings_for_zha_ts1201,
)
from .learn import (
    learn_once,
    read_learned_code_on_demand,
    start_learn_mode,
    stop_learn_mode,
)
from .migration import async_migrate_entry
from .remote_events import async_setup_remote_button_listener
from .signal_log.api import async_register_signal_log_api
from .signal_log.ha_bridge import (
    async_setup_inbound_listener,
    async_start_inbound_capture,
    async_stop_inbound_capture,
    log_outbound_send,
)
from .signal_log.panel import async_register_signal_log_panel
from .ui_api import async_register_easyir_ui_api
from .transports import Ts1201ZhaTransport
from .transports.base import IrTransport, TransportSendContext

_LOGGER = logging.getLogger(__name__)


async def _async_encode_profile_command_for_transport(
    hass: HomeAssistant,
    *,
    profile_path: str,
    action: str,
    hvac_mode: str | None,
    fan_mode: str | None,
    temperature: int | None,
):
    """Run sync profile resolution in executor to keep loop non-blocking."""
    encode_call = partial(
        encode_profile_command_for_zha_ts1201,
        profile_path=profile_path,
        action=action,
        hvac_mode=hvac_mode,
        fan_mode=fan_mode,
        temperature=temperature,
    )
    return await hass.async_add_executor_job(encode_call)


def _resolve_hub_from_call(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    hub_id = str(call.data.get(CONF_HUB_ID, "")).strip() or None
    ieee = call.data.get(CONF_IEEE)
    if ieee is not None:
        ieee = str(ieee).strip() or None

    if hub_id:
        hub = hub_ref_by_id(hass, hub_id)
        if hub is None:
            raise vol.Invalid(f"Unknown hub_id: {hub_id}")
        if ieee and ieee.lower().replace(" ", "") != str(hub.data[CONF_IEEE]).lower().replace(" ", ""):
            raise vol.Invalid("hub_id and ieee refer to different hubs")
        return hub_transport_data(hub)

    if ieee:
        hub = hub_ref_for_ieee(hass, ieee)
        if hub is None:
            raise vol.Invalid(f"No EasyIR hub configured for ieee: {ieee}")
        return hub_transport_data(hub)

    hubs = iter_hub_refs(hass)
    if len(hubs) == 1:
        return hub_transport_data(hubs[0])
    raise vol.Invalid("Missing hub target: provide hub_id or ieee")


SEND_RAW_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HUB_ID): cv.string,
        vol.Optional(CONF_IEEE): cv.string,
        vol.Required("raw_timings"): vol.All(cv.ensure_list, [vol.Coerce(int)]),
        vol.Optional(CONF_ENDPOINT_ID, default=DEFAULT_ENDPOINT_ID): vol.Coerce(int),
    }
)

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HUB_ID): cv.string,
        vol.Optional(CONF_IEEE): cv.string,
        vol.Optional(CONF_PROFILE_PATH): cv.string,
        vol.Required("action"): cv.string,
        vol.Optional("hvac_mode"): cv.string,
        vol.Optional("fan_mode"): cv.string,
        vol.Optional("temperature"): vol.Coerce(int),
        vol.Optional(CONF_ENDPOINT_ID, default=DEFAULT_ENDPOINT_ID): vol.Coerce(int),
    }
)

LEARN_TARGET_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HUB_ID): cv.string,
        vol.Optional(CONF_IEEE): cv.string,
        vol.Optional(CONF_ENDPOINT_ID): vol.Coerce(int),
        vol.Optional("timeout_s", default=20): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=120)
        ),
        vol.Optional("timeout_seconds"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=120)
        ),
    }
)

CAPTURE_INBOUND_SCHEMA = vol.Schema(
    {
        vol.Optional("duration_s", default=30): vol.All(
            vol.Coerce(float), vol.Range(min=1, max=300)
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up services for the integration."""
    root = hass.data.setdefault(DOMAIN, {})
    root.setdefault("climate_entities", {})
    root.setdefault("remote_buttons", {})
    root.setdefault("ir_transport", Ts1201ZhaTransport())
    root.setdefault("service_call_pool_interval_s", DEFAULT_POOL_INTERVAL_S)
    get_service_call_pool(hass)
    async_setup_inbound_listener(hass)
    async_setup_remote_button_listener(hass)
    async_register_signal_log_api(hass)
    async_register_easyir_ui_api(hass)
    async_schedule_hub_discovery(hass)

    async def handle_send_raw(call: ServiceCall) -> None:
        hub = _resolve_hub_from_call(hass, call)
        ieee = hub[CONF_IEEE]
        endpoint_id = int(call.data.get(CONF_ENDPOINT_ID) or hub.get(CONF_ENDPOINT_ID) or TS1201_ENDPOINT_ID)
        raw_timings = call.data["raw_timings"]
        frame, code = encode_raw_timings_for_zha_ts1201(raw_timings)
        transport: IrTransport = hass.data[DOMAIN]["ir_transport"]
        await transport.send(
            hass,
            code,
            TransportSendContext(ieee=ieee, endpoint_id=endpoint_id),
        )
        log_outbound_send(
            hass,
            ieee=ieee,
            timings=frame.timings,
            entity_id=None,
            entry_data=hub,
            protocol_hint="raw_timings",
        )

    async def handle_send_command(call: ServiceCall) -> None:
        profile_path = call.data.get(CONF_PROFILE_PATH)
        if not profile_path:
            raise vol.Invalid("Missing required 'profile_path' in service data")

        hub = _resolve_hub_from_call(hass, call)
        ieee = hub[CONF_IEEE]
        endpoint_id = int(call.data.get(CONF_ENDPOINT_ID) or hub.get(CONF_ENDPOINT_ID) or TS1201_ENDPOINT_ID)
        frame, code = await _async_encode_profile_command_for_transport(
            hass,
            profile_path=str(profile_path),
            action=call.data["action"],
            hvac_mode=call.data.get("hvac_mode"),
            fan_mode=call.data.get("fan_mode"),
            temperature=call.data.get("temperature"),
        )
        transport: IrTransport = hass.data[DOMAIN]["ir_transport"]
        await transport.send(
            hass,
            code,
            TransportSendContext(ieee=ieee, endpoint_id=endpoint_id),
        )
        log_outbound_send(
            hass,
            ieee=ieee,
            timings=frame.timings,
            entity_id=None,
            entry_data=hub,
            protocol_hint="profile",
        )

    async def handle_start_learn(call: ServiceCall) -> None:
        hub_id = str(call.data.get(CONF_HUB_ID, "")).strip() or None
        ieee = call.data.get(CONF_IEEE)
        if ieee is not None:
            ieee = str(ieee).strip() or None
        endpoint_id = call.data.get(CONF_ENDPOINT_ID)
        timeout_s = int(call.data.get("timeout_s") or call.data.get("timeout_seconds") or 20)
        await start_learn_mode(
            hass,
            hub_id=hub_id,
            ieee=ieee,
            endpoint_id=int(endpoint_id) if endpoint_id is not None else None,
            timeout_s=timeout_s,
        )

    async def handle_read_learned(call: ServiceCall) -> dict[str, Any]:
        hub_id = str(call.data.get(CONF_HUB_ID, "")).strip() or None
        ieee = call.data.get(CONF_IEEE)
        if ieee is not None:
            ieee = str(ieee).strip() or None
        endpoint_id = call.data.get(CONF_ENDPOINT_ID)
        return await read_learned_code_on_demand(
            hass,
            hub_id=hub_id,
            ieee=ieee,
            endpoint_id=int(endpoint_id) if endpoint_id is not None else None,
        )

    async def handle_stop_learn(call: ServiceCall) -> None:
        hub_id = str(call.data.get(CONF_HUB_ID, "")).strip() or None
        ieee = call.data.get(CONF_IEEE)
        if ieee is not None:
            ieee = str(ieee).strip() or None
        await stop_learn_mode(hass, hub_id=hub_id, ieee=ieee)

    async def handle_learn_once(call: ServiceCall) -> None:
        hub_id = str(call.data.get(CONF_HUB_ID, "")).strip() or None
        ieee = call.data.get(CONF_IEEE)
        if ieee is not None:
            ieee = str(ieee).strip() or None
        if not hub_id and not ieee:
            raise vol.Invalid(
                "Missing learn target: provide 'hub_id' or 'ieee'"
            )
        endpoint_id = call.data.get(CONF_ENDPOINT_ID)
        timeout_s = int(call.data.get("timeout_s") or call.data.get("timeout_seconds") or 20)
        hass.bus.async_fire(
            DEBUG_EVENT_LEARN_ONCE_HANDLER_ENTER,
            {
                "hub_id": hub_id,
                "ieee": str(ieee) if ieee else None,
                "endpoint_id": int(endpoint_id) if endpoint_id is not None else None,
                "timeout_s": timeout_s,
            },
        )
        await learn_once(
            hass,
            hub_id=hub_id,
            ieee=str(ieee) if ieee else None,
            endpoint_id=int(endpoint_id) if endpoint_id is not None else None,
            timeout_s=timeout_s,
        )

    async def handle_capture_inbound(call: ServiceCall) -> None:
        duration_s = float(call.data.get("duration_s", 30))
        async_start_inbound_capture(hass, duration_s=duration_s)

    hass.services.async_register(DOMAIN, SERVICE_SEND_RAW, handle_send_raw, schema=SEND_RAW_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_SEND_COMMAND, handle_send_command, schema=SEND_COMMAND_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_START_LEARN, handle_start_learn, schema=LEARN_TARGET_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_READ_LEARNED,
        handle_read_learned,
        schema=LEARN_TARGET_SCHEMA,
        supports_response=True,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_STOP_LEARN, handle_stop_learn, schema=LEARN_TARGET_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LEARN_ONCE, handle_learn_once, schema=LEARN_TARGET_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_LEARN_CODE_LEGACY, handle_learn_once, schema=LEARN_TARGET_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CAPTURE_INBOUND,
        handle_capture_inbound,
        schema=CAPTURE_INBOUND_SCHEMA,
    )

    return True


async def _async_entry_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Keep EasyIR device tree in sync after entry/subentry changes."""
    await async_setup_devices_for_entry(hass, entry)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the single EasyIR parent config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("climate_entities", {})
    hass.data[DOMAIN].setdefault("remote_buttons", {})
    hass.data[DOMAIN].setdefault("ir_transport", Ts1201ZhaTransport())
    hass.data[DOMAIN][entry.entry_id] = entry
    entry.async_on_unload(entry.add_update_listener(_async_entry_update_listener))

    await async_setup_devices_for_entry(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_signal_log_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the EasyIR parent config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
