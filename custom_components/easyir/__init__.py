"""EasyIR custom integration."""

from __future__ import annotations

from functools import partial
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .config_flow import EasyIrConfigFlow
from .const import (
    CONF_ENDPOINT_ID,
    CONF_HUB_ID,
    CONF_IEEE,
    CONF_PROFILE_PATH,
    DEBUG_EVENT_LEARN_ONCE_HANDLER_ENTER,
    DEFAULT_ENDPOINT_ID,
    DOMAIN,
    PLATFORMS,
    SERVICE_LEARN_CODE_LEGACY,
    SERVICE_SEND_RAW,
    SERVICE_SEND_COMMAND,
    SERVICE_LEARN_ONCE,
    TS1201_ENDPOINT_ID,
)
from .command_pool import DEFAULT_POOL_INTERVAL_S, get_service_call_pool
from .ir_core.service_adapter import (
    encode_profile_command_for_zha_ts1201,
    encode_raw_timings_for_zha_ts1201,
)
from .signal_log.api import async_register_signal_log_api
from .signal_log.ha_bridge import async_setup_inbound_listener, log_outbound_send
from .signal_log.panel import async_register_signal_log_panel
from .learn import learn_once
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


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate stored config when EasyIrConfigFlow.VERSION changes.

    v1 entries matched the historical MVP shape. v2 keeps the same keys but
    guarantees ``endpoint_id`` is present for service default merging.
    """
    if entry.version > EasyIrConfigFlow.VERSION:
        return False

    data = dict(entry.data)
    if entry.version < 2:
        data.setdefault(CONF_ENDPOINT_ID, DEFAULT_ENDPOINT_ID)

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        version=EasyIrConfigFlow.VERSION,
        minor_version=EasyIrConfigFlow.MINOR_VERSION,
    )
    return True


def _entry_data_for_ieee(hass: HomeAssistant, ieee: str) -> dict[str, Any] | None:
    """Return merged config entry data for the EasyIR entry matching ieee."""
    norm = ieee.lower().replace(" ", "")
    for entry in hass.config_entries.async_entries(DOMAIN):
        e = str(entry.data.get(CONF_IEEE, "")).lower().replace(" ", "")
        if e == norm:
            return dict(entry.data)
    return None


SEND_RAW_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_IEEE): cv.string,
        vol.Required("raw_timings"): vol.All(cv.ensure_list, [vol.Coerce(int)]),
        vol.Optional(CONF_ENDPOINT_ID, default=DEFAULT_ENDPOINT_ID): vol.Coerce(int),
    }
)

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_IEEE): cv.string,
        vol.Optional(CONF_PROFILE_PATH): cv.string,
        vol.Required("action"): cv.string,
        vol.Optional("hvac_mode"): cv.string,
        vol.Optional("fan_mode"): cv.string,
        vol.Optional("temperature"): vol.Coerce(int),
        vol.Optional(CONF_ENDPOINT_ID, default=DEFAULT_ENDPOINT_ID): vol.Coerce(int),
    }
)

LEARN_ONCE_SCHEMA = vol.Schema(
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

LEARN_CODE_LEGACY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HUB_ID): cv.string,
        vol.Optional(CONF_IEEE): cv.string,
        vol.Optional(CONF_ENDPOINT_ID): vol.Coerce(int),
        vol.Optional("timeout_seconds", default=20): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=120)
        ),
        vol.Optional("timeout_s"): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up services for the integration."""
    root = hass.data.setdefault(DOMAIN, {})
    root.setdefault("climate_entities", {})
    root.setdefault("ir_transport", Ts1201ZhaTransport())
    root.setdefault("service_call_pool_interval_s", DEFAULT_POOL_INTERVAL_S)
    get_service_call_pool(hass)
    async_setup_inbound_listener(hass)
    async_register_signal_log_api(hass)

    def _default_data() -> dict[str, Any]:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return {}
        return entries[0].data

    def _get_merged_value(call: ServiceCall, key: str) -> Any:
        if key in call.data:
            return call.data[key]
        return _default_data().get(key)

    async def handle_send_raw(call: ServiceCall) -> None:
        ieee = _get_merged_value(call, CONF_IEEE)
        if not ieee:
            raise vol.Invalid("Missing required 'ieee' in service data or config entry")

        endpoint_id = _get_merged_value(call, CONF_ENDPOINT_ID) or TS1201_ENDPOINT_ID
        raw_timings = call.data["raw_timings"]
        frame, code = encode_raw_timings_for_zha_ts1201(raw_timings)
        _LOGGER.debug("Generated Tuya code for %s: %s", ieee, code)
        transport: IrTransport = hass.data[DOMAIN]["ir_transport"]
        await transport.send(
            hass,
            code,
            TransportSendContext(ieee=ieee, endpoint_id=endpoint_id),
        )
        entry_data = _entry_data_for_ieee(hass, ieee) or {}
        log_outbound_send(
            hass,
            ieee=ieee,
            timings=frame.timings,
            entity_id=None,
            entry_data=entry_data,
            protocol_hint="raw_timings",
        )

    async def handle_send_command(call: ServiceCall) -> None:
        ieee = _get_merged_value(call, CONF_IEEE)
        if not ieee:
            raise vol.Invalid("Missing required 'ieee' in service data or config entry")

        profile_path = _get_merged_value(call, CONF_PROFILE_PATH)
        if not profile_path:
            raise vol.Invalid(
                "Missing required 'profile_path' in service data or config entry"
            )

        endpoint_id = _get_merged_value(call, CONF_ENDPOINT_ID) or TS1201_ENDPOINT_ID
        frame, code = await _async_encode_profile_command_for_transport(
            hass,
            profile_path=profile_path,
            action=call.data["action"],
            hvac_mode=call.data.get("hvac_mode"),
            fan_mode=call.data.get("fan_mode"),
            temperature=call.data.get("temperature"),
        )
        _LOGGER.debug(
            "Generated profile->Tuya code for %s action=%s",
            ieee,
            call.data["action"],
        )
        transport: IrTransport = hass.data[DOMAIN]["ir_transport"]
        await transport.send(
            hass,
            code,
            TransportSendContext(ieee=ieee, endpoint_id=endpoint_id),
        )
        entry_data = _entry_data_for_ieee(hass, ieee) or {}
        log_outbound_send(
            hass,
            ieee=ieee,
            timings=frame.timings,
            entity_id=None,
            entry_data=entry_data,
            protocol_hint="profile",
        )

    async def handle_learn_once(call: ServiceCall) -> None:
        hub_id = str(call.data.get(CONF_HUB_ID, "")).strip() or None
        if hub_id:
            ieee = call.data.get(CONF_IEEE)
        else:
            ieee = _get_merged_value(call, CONF_IEEE)
        if ieee is not None:
            ieee = str(ieee).strip() or None
        if not hub_id and not ieee:
            raise vol.Invalid(
                "Missing learn target: provide 'hub_id' or 'ieee' (or configure default entry)"
            )
        endpoint_id = call.data.get(CONF_ENDPOINT_ID)
        timeout_s = int(call.data.get("timeout_s") or call.data.get("timeout_seconds") or 20)
        _LOGGER.warning(
            "EasyIR learn_once handler start hub_id=%s ieee=%s endpoint=%s timeout_s=%s",
            hub_id,
            ieee,
            endpoint_id,
            timeout_s,
        )
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

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_RAW,
        handle_send_raw,
        schema=SEND_RAW_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        handle_send_command,
        schema=SEND_COMMAND_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LEARN_ONCE,
        handle_learn_once,
        schema=LEARN_ONCE_SCHEMA,
    )
    # Backward-compatible alias for old service naming used in early UI/docs.
    hass.services.async_register(
        DOMAIN,
        SERVICE_LEARN_CODE_LEGACY,
        handle_learn_once,
        schema=LEARN_CODE_LEGACY_SCHEMA,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EasyIR from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("climate_entities", {})
    hass.data[DOMAIN].setdefault("ir_transport", Ts1201ZhaTransport())
    hass.data[DOMAIN][entry.entry_id] = entry.data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_signal_log_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
