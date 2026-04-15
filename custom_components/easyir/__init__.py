"""EasyIR custom integration."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ENDPOINT_ID,
    CONF_IEEE,
    CONF_PROFILE_PATH,
    DEFAULT_ENDPOINT_ID,
    DEFAULT_SEND_DELAY_MS,
    DOMAIN,
    PLATFORMS,
    SERVICE_SEND_RAW,
    SERVICE_SEND_COMMAND,
    TS1201_CLUSTER_ID,
    TS1201_CLUSTER_TYPE,
    TS1201_COMMAND_ID,
    TS1201_COMMAND_TYPE,
    TS1201_ENDPOINT_ID,
    ZHA_DOMAIN,
    ZHA_SERVICE,
)
from .helpers import encode_raw_to_tuya_base64, resolve_profile_raw
from .signal_log.ha_bridge import async_setup_inbound_listener, log_outbound_send

_LOGGER = logging.getLogger(__name__)


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


async def _send_tuya_ir(
    hass: HomeAssistant,
    ieee: str,
    code: str,
    endpoint_id: int,
) -> None:
    """Proxy send to zha.issue_zigbee_cluster_command."""
    payload: dict[str, Any] = {
        "ieee": ieee,
        "endpoint_id": endpoint_id,
        "cluster_id": TS1201_CLUSTER_ID,
        "cluster_type": TS1201_CLUSTER_TYPE,
        "command": TS1201_COMMAND_ID,
        "command_type": TS1201_COMMAND_TYPE,
        "params": {"code": code},
    }
    await hass.services.async_call(
        ZHA_DOMAIN,
        ZHA_SERVICE,
        payload,
        blocking=True,
    )


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up services for the integration."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("climate_entities", {})
    async_setup_inbound_listener(hass)
    send_lock_by_ieee: dict[str, asyncio.Lock] = {}
    last_send_by_ieee: dict[str, float] = {}

    def _default_data() -> dict[str, Any]:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return {}
        return entries[0].data

    def _get_merged_value(call: ServiceCall, key: str) -> Any:
        if key in call.data:
            return call.data[key]
        return _default_data().get(key)

    async def _apply_rate_limit(ieee: str) -> None:
        lock = send_lock_by_ieee.setdefault(ieee, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            delay_s = DEFAULT_SEND_DELAY_MS / 1000.0
            last_send = last_send_by_ieee.get(ieee, 0.0)
            wait_s = delay_s - (now - last_send)
            if wait_s > 0:
                await asyncio.sleep(wait_s)
            last_send_by_ieee[ieee] = time.monotonic()

    async def handle_send_raw(call: ServiceCall) -> None:
        ieee = _get_merged_value(call, CONF_IEEE)
        if not ieee:
            raise vol.Invalid("Missing required 'ieee' in service data or config entry")

        endpoint_id = _get_merged_value(call, CONF_ENDPOINT_ID) or TS1201_ENDPOINT_ID
        raw_timings = call.data["raw_timings"]
        code = encode_raw_to_tuya_base64(raw_timings)
        _LOGGER.debug("Generated Tuya code for %s: %s", ieee, code)
        await _apply_rate_limit(ieee)
        await _send_tuya_ir(hass, ieee, code, endpoint_id)
        entry_data = _entry_data_for_ieee(hass, ieee) or {}
        log_outbound_send(
            hass,
            ieee=ieee,
            timings=raw_timings,
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
        raw_timings = resolve_profile_raw(
            path=profile_path,
            action=call.data["action"],
            hvac_mode=call.data.get("hvac_mode"),
            fan_mode=call.data.get("fan_mode"),
            temperature=call.data.get("temperature"),
        )
        code = encode_raw_to_tuya_base64(raw_timings)
        _LOGGER.debug(
            "Generated profile->Tuya code for %s action=%s",
            ieee,
            call.data["action"],
        )
        await _apply_rate_limit(ieee)
        await _send_tuya_ir(hass, ieee, code, endpoint_id)
        entry_data = _entry_data_for_ieee(hass, ieee) or {}
        log_outbound_send(
            hass,
            ieee=ieee,
            timings=raw_timings,
            entity_id=None,
            entry_data=entry_data,
            protocol_hint="profile",
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

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EasyIR from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("climate_entities", {})
    hass.data[DOMAIN][entry.entry_id] = entry.data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
