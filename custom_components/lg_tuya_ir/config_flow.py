"""Config flow for EasyIR integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_ENDPOINT_ID, CONF_IEEE, CONF_PROFILE_PATH, DEFAULT_ENDPOINT_ID, DOMAIN


class LgTuyaIrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EasyIR."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="EasyIR", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_IEEE): str,
                vol.Required(CONF_PROFILE_PATH): str,
                vol.Optional(CONF_ENDPOINT_ID, default=DEFAULT_ENDPOINT_ID): vol.All(
                    int, vol.Range(min=1, max=240)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema)
