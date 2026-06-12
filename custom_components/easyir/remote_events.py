"""Remote button events: press, state sync, and IR dispatch to hubs."""

from __future__ import annotations

import logging
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_BUTTON_KEY,
    CONF_ENDPOINT_ID,
    CONF_PROFILE_PATH,
    CONF_STATE_CHANGE_ONLY,
    DOMAIN,
    EVENT_REMOTE_BUTTON_COMMAND,
    EVENT_REMOTE_BUTTON_PRESSED,
)
from .hub_registry import hub_entries_for_remote, hub_transport_data
from .ir_core.service_adapter import encode_profile_command_for_zha_ts1201
from .signal_log.ha_bridge import log_outbound_send
from .transports.base import IrTransport, TransportSendContext

_LOGGER = logging.getLogger(__name__)


async def async_send_profile_to_hubs(
    hass: HomeAssistant,
    *,
    remote_entry: ConfigEntry,
    action: str,
    hvac_mode: str | None = None,
    fan_mode: str | None = None,
    temperature: int | None = None,
    entity_id: str | None = None,
) -> None:
    """Resolve profile command and transmit through every hub linked to the remote."""
    profile_path = str(remote_entry.data[CONF_PROFILE_PATH])
    encode_call = partial(
        encode_profile_command_for_zha_ts1201,
        profile_path=profile_path,
        action=action,
        hvac_mode=hvac_mode,
        fan_mode=fan_mode,
        temperature=temperature,
    )
    frame, code = await hass.async_add_executor_job(encode_call)
    transport: IrTransport = hass.data[DOMAIN]["ir_transport"]
    for hub in hub_entries_for_remote(hass, remote_entry):
        hub_data = hub_transport_data(hub)
        ieee = hub_data["ieee"]
        endpoint_id = int(hub_data.get(CONF_ENDPOINT_ID, 1))
        await transport.send(
            hass,
            code,
            TransportSendContext(ieee=ieee, endpoint_id=endpoint_id),
        )
        log_outbound_send(
            hass,
            ieee=ieee,
            timings=frame.timings,
            entity_id=entity_id,
            entry_data=dict(hub.data),
            protocol_hint="remote_button",
        )


@callback
def async_fire_button_pressed(
    hass: HomeAssistant,
    *,
    remote_entry_id: str,
    button_key: str,
    send_ir: bool,
    state_change_only: bool,
    entity_id: str | None = None,
) -> None:
    """Notify automations that a remote button was activated."""
    hass.bus.async_fire(
        EVENT_REMOTE_BUTTON_PRESSED,
        {
            "remote_entry_id": remote_entry_id,
            "button_key": button_key,
            "send_ir": send_ir,
            "state_change_only": state_change_only,
            "entity_id": entity_id,
        },
    )


@callback
def async_setup_remote_button_listener(hass: HomeAssistant) -> None:
    """Listen for external button commands (automations / inbound IR sync)."""
    if hass.data.get(DOMAIN, {}).get("_remote_button_listener_ready"):
        return
    hass.data.setdefault(DOMAIN, {})["_remote_button_listener_ready"] = True

    @callback
    def _on_command(event) -> None:
        data = event.data if isinstance(event.data, dict) else {}
        remote_entry_id = str(data.get("remote_entry_id", "")).strip()
        button_key = str(data.get(CONF_BUTTON_KEY, data.get("button_key", ""))).strip()
        if not remote_entry_id or not button_key:
            return
        state_change_only = bool(data.get(CONF_STATE_CHANGE_ONLY, False))
        send_ir = not state_change_only and bool(data.get(CONF_SEND_IR, True))
        buttons = hass.data.get(DOMAIN, {}).get("remote_buttons", {})
        entity = buttons.get((remote_entry_id, button_key))
        if entity is None:
            _LOGGER.debug(
                "No remote button entity for remote=%s key=%s", remote_entry_id, button_key
            )
            return
        hass.async_create_task(
            entity.async_handle_external_command(send_ir=send_ir, state_change_only=state_change_only)
        )

    hass.bus.async_listen(EVENT_REMOTE_BUTTON_COMMAND, _on_command)
