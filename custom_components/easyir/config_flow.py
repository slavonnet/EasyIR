"""Config flow for EasyIR integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .bundled_profiles import (
    PROFILE_CUSTOM,
    resolve_stored_profile_path,
    select_selector_options,
)
from .const import (
    CONF_ENDPOINT_ID,
    CONF_IEEE,
    CONF_PROFILE_CHOICE,
    CONF_PROFILE_PATH,
    DEFAULT_ENDPOINT_ID,
    DOMAIN,
)
from .supported_hubs import list_onboarding_hub_choices

CONF_ZHA_DEVICE = "zha_device"
ZHA_DOMAIN = "zha"


def _ieee_from_zha_device(device: dr.DeviceEntry) -> str | None:
    """Extract Zigbee IEEE from a ZHA device registry entry."""
    for domain, value in device.identifiers:
        if domain == ZHA_DOMAIN:
            return str(value)
    for conn_kind, value in device.connections:
        if conn_kind == "zigbee":
            return str(value)
    return None


class EasyIrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EasyIR."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if not self.hass.config_entries.async_entries(ZHA_DOMAIN):
            return self.async_abort(reason="zha_not_configured")

        errors: dict[str, str] = {}
        profile_options = select_selector_options()
        default_profile = profile_options[0]["value"] if profile_options else PROFILE_CUSTOM

        if user_input is not None:
            device_reg = dr.async_get(self.hass)
            zha_device_id = user_input[CONF_ZHA_DEVICE]
            device = device_reg.async_get(zha_device_id)
            if device is None:
                errors["base"] = "invalid_device"
            else:
                ieee = _ieee_from_zha_device(device)
                if ieee is None or ieee == "":
                    errors["base"] = "unknown_ieee"

            profile_choice = user_input.get(CONF_PROFILE_CHOICE, default_profile)
            custom_path = user_input.get(CONF_PROFILE_PATH)
            resolved_path: str | None = None
            if not errors:
                try:
                    resolved_path = resolve_stored_profile_path(
                        str(profile_choice), custom_path
                    )
                except ValueError:
                    errors["base"] = "invalid_profile"

            if not errors and resolved_path is not None:
                unique_id = ieee.lower().replace(" ", "")
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="EasyIR",
                    data={
                        CONF_IEEE: ieee,
                        CONF_PROFILE_PATH: resolved_path,
                        CONF_ENDPOINT_ID: int(
                            user_input.get(CONF_ENDPOINT_ID, DEFAULT_ENDPOINT_ID)
                        ),
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ZHA_DEVICE): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        integration=ZHA_DOMAIN,
                        filter=[
                            {
                                "integration": ZHA_DOMAIN,
                                "model": "TS1201",
                            }
                        ],
                    )
                ),
                vol.Required(CONF_PROFILE_CHOICE, default=default_profile): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=profile_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_PROFILE_PATH): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                    )
                ),
                vol.Optional(
                    CONF_ENDPOINT_ID, default=DEFAULT_ENDPOINT_ID
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=240,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        description_placeholders: dict[str, str] = {}
        supported = list_onboarding_hub_choices(self.hass)
        if supported:
            lines = "\n".join(f"- {label}" for _, label in supported[:8])
            if len(supported) > 8:
                lines += "\n- …"
            description_placeholders["optional_supported"] = (
                "\n\nSupported TS1201 hubs detected (not yet in EasyIR):\n" + lines
            )
        else:
            description_placeholders["optional_supported"] = ""

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )
