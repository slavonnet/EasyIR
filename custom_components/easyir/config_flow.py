"""Config flow for EasyIR integration (hub-centric model)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .bundled_profiles import (
    PROFILE_CUSTOM,
    async_select_selector_options,
    resolve_stored_profile_path,
)
from .const import (
    CONF_ENDPOINT_ID,
    CONF_ENTRY_KIND,
    CONF_HUB_ENTRY_ID,
    CONF_HUB_IDS,
    CONF_IEEE,
    CONF_PROFILE_CHOICE,
    CONF_PROFILE_PATH,
    CONF_REMOTE_NAME,
    CONF_TRANSPORT,
    DEFAULT_ENDPOINT_ID,
    DOMAIN,
    ENTRY_KIND_HUB,
    ENTRY_KIND_REMOTE,
    FLOW_SOURCE_ADD_HUB,
    FLOW_SOURCE_ADD_REMOTE,
    FLOW_SOURCE_HUB_REMOTE,
    TRANSPORT_TS1201_ZHA,
    ZHA_DOMAIN,
)
from .endpoint import endpoint_for_ieee, endpoint_for_zha_device
from .hub_registry import hub_entry_by_id, is_hub_entry, iter_hub_entries
from .supported_hubs import ieee_from_zha_device, list_onboarding_hub_choices

CONF_ZHA_DEVICE = "zha_device"
CONF_HUB_PICK = "hub_pick"
MENU_MANUAL = "manual"


def _ieee_from_zha_device(device: dr.DeviceEntry) -> str | None:
    return ieee_from_zha_device(device)


class EasyIrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EasyIR."""

    VERSION = 3
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._hub_ieee: str | None = None
        self._hub_device_name: str | None = None
        self._prefill_hub_entry_id: str | None = None
        self._pending_hub_endpoint_id: int | None = None

    async def _async_manual_hub_pick_label(self) -> str:
        from homeassistant.helpers import translation

        strings = await translation.async_get_translations(
            self.hass,
            self.hass.config.language,
            "config",
            integrations=[DOMAIN],
        )
        return strings.get(
            f"component.{DOMAIN}.config.step.user.options.manual",
            "Select ZHA device manually",
        )

    async def _async_menu_label(self, option_key: str) -> str:
        from homeassistant.helpers import translation

        strings = await translation.async_get_translations(
            self.hass,
            self.hass.config.language,
            "config",
            integrations=[DOMAIN],
        )
        return strings.get(
            f"component.{DOMAIN}.config.step.main_menu.menu_options.{option_key}",
            option_key,
        )

    async def async_step_import(self, user_input: dict[str, Any]) -> FlowResult:
        """Import remote entry during v2→v3 migration."""
        hub_entry_id = str(user_input.get(CONF_HUB_ENTRY_ID, "")).strip()
        profile_path = str(user_input.get(CONF_PROFILE_PATH, "")).strip()
        unique_id = str(user_input.get("unique_id", "")).strip() or None
        if not hub_entry_id or not profile_path:
            return self.async_abort(reason="invalid_import")
        if unique_id:
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
        return await self._async_create_remote_entry(
            hub_entry_id=hub_entry_id,
            profile_path=profile_path,
            remote_name=None,
        )

    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> FlowResult:
        """Handle discovered IR hub (TS1201 via ZHA) on first EasyIR setup."""
        return await self._async_begin_hub_from_discovery(discovery_info)

    async def async_step_add_hub(
        self, discovery_info: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add another hub (menu or discovered unconfigured TS1201)."""
        if discovery_info:
            return await self._async_begin_hub_from_discovery(discovery_info)
        return await self._async_step_pick_hub(None)

    async def _async_begin_hub_from_discovery(
        self, discovery_info: dict[str, Any]
    ) -> FlowResult:
        device_id = str(discovery_info.get("device_id", "")).strip()
        ieee = str(discovery_info.get("ieee", "")).strip() or None
        device_reg = dr.async_get(self.hass)
        if device_id:
            device = device_reg.async_get(device_id)
            if device is not None:
                ieee = ieee or _ieee_from_zha_device(device)
                self._hub_device_name = device.name_by_user or device.name
        if ieee is None:
            return self.async_abort(reason="unknown_ieee")
        self._hub_ieee = ieee
        self.context["hub_endpoint_id"] = endpoint_for_ieee(self.hass, ieee)
        await self.async_set_unique_id(ieee.lower().replace(" ", ""))
        self._abort_if_unique_id_configured()
        return await self.async_step_hub_confirm()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Default entry: main menu (add hub / add remote)."""
        source = str(self.context.get("source", "")).strip()
        if source == FLOW_SOURCE_HUB_REMOTE:
            self._prefill_hub_entry_id = str(
                self.context.get("hub_entry_id", "")
            ).strip() or None
            return await self.async_step_hub_remote()
        if source == FLOW_SOURCE_ADD_HUB:
            return await self.async_step_add_hub(user_input)
        return await self.async_step_main_menu()

    async def async_step_main_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Top-level actions: add IR hub or add virtual remote."""
        if user_input == FLOW_SOURCE_ADD_HUB:
            if not self.hass.config_entries.async_entries(ZHA_DOMAIN):
                return self.async_abort(reason="zha_not_configured")
            return await self._async_step_pick_hub(None)
        if user_input == FLOW_SOURCE_ADD_REMOTE:
            if not iter_hub_entries(self.hass):
                return self.async_abort(reason="hub_not_found")
            return await self.async_step_hub_remote()

        add_hub_label = await self._async_menu_label(FLOW_SOURCE_ADD_HUB)
        add_remote_label = await self._async_menu_label(FLOW_SOURCE_ADD_REMOTE)
        return self.async_show_menu(
            step_id="main_menu",
            menu_options={
                FLOW_SOURCE_ADD_HUB: add_hub_label,
                FLOW_SOURCE_ADD_REMOTE: add_remote_label,
            },
        )

    async def _async_step_pick_hub(
        self, user_input: dict[str, Any] | None
    ) -> FlowResult:
        """Pick a discovered TS1201 hub or open manual ZHA device selection."""
        discovered = list_onboarding_hub_choices(self.hass)
        if not discovered:
            return await self.async_step_hub_manual()

        if user_input is not None:
            pick = str(user_input.get(CONF_HUB_PICK, "")).strip()
            if pick == MENU_MANUAL:
                return await self.async_step_hub_manual()
            device_reg = dr.async_get(self.hass)
            device = device_reg.async_get(pick)
            if device is None:
                return self.async_abort(reason="invalid_device")
            ieee = _ieee_from_zha_device(device)
            if ieee is None:
                return self.async_abort(reason="unknown_ieee")
            self._hub_ieee = ieee
            self._hub_device_name = device.name_by_user or device.name
            self.context["hub_endpoint_id"] = endpoint_for_zha_device(device)
            await self.async_set_unique_id(ieee.lower().replace(" ", ""))
            self._abort_if_unique_id_configured()
            return await self.async_step_hub_confirm()

        manual_label = await self._async_manual_hub_pick_label()
        select_options = [
            {"value": dev_id, "label": label} for dev_id, label in discovered
        ]
        select_options.append({"value": MENU_MANUAL, "label": manual_label})
        data_schema = vol.Schema(
            {
                vol.Required(CONF_HUB_PICK): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=select_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            description_placeholders={"count": str(len(discovered))},
        )

    async def async_step_hub_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manual ZHA device picker for IR hub."""
        errors: dict[str, str] = {}
        if user_input is not None:
            device_reg = dr.async_get(self.hass)
            device = device_reg.async_get(user_input[CONF_ZHA_DEVICE])
            if device is None:
                errors["base"] = "invalid_device"
            else:
                ieee = _ieee_from_zha_device(device)
                if ieee is None or ieee == "":
                    errors["base"] = "unknown_ieee"
                else:
                    self._hub_ieee = ieee
                    self._hub_device_name = device.name_by_user or device.name
                    self.context["hub_endpoint_id"] = endpoint_for_zha_device(device)
                    await self.async_set_unique_id(ieee.lower().replace(" ", ""))
                    self._abort_if_unique_id_configured()
                    return await self.async_step_hub_confirm()

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
            }
        )
        return self.async_show_form(
            step_id="hub_manual",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_hub_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm hub and optionally continue to remote profile in the same flow."""
        errors: dict[str, str] = {}
        if self._hub_ieee is None:
            return self.async_abort(reason="unknown_ieee")

        if user_input is not None:
            if self.context.get("hub_endpoint_id") is None and self._hub_ieee:
                self.context["hub_endpoint_id"] = endpoint_for_ieee(
                    self.hass, self._hub_ieee
                )
            endpoint_id = int(
                self.context.get("hub_endpoint_id", DEFAULT_ENDPOINT_ID)
            )
            if bool(user_input.get("add_remote")):
                self._pending_hub_endpoint_id = endpoint_id
                return await self.async_step_hub_remote()
            return self._async_create_hub_entry(endpoint_id=endpoint_id)

        if self.context.get("hub_endpoint_id") is None and self._hub_ieee:
            self.context["hub_endpoint_id"] = endpoint_for_ieee(
                self.hass, self._hub_ieee
            )

        data_schema = vol.Schema(
            {
                vol.Required("add_remote", default=False): selector.BooleanSelector(),
            }
        )
        title = self._hub_device_name or self._hub_ieee
        return self.async_show_form(
            step_id="hub_confirm",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"hub_name": title or ""},
        )

    def _async_resolve_hub_for_remote(
        self, user_input: dict[str, Any] | None
    ) -> config_entries.ConfigEntry | None:
        """Pick hub from flow context, form input, or single configured hub."""
        hub_entry_id = str(
            self.context.get("hub_entry_id")
            or self._prefill_hub_entry_id
            or ""
        ).strip()
        if user_input is not None:
            picked = str(user_input.get(CONF_HUB_ENTRY_ID, "")).strip()
            if picked:
                hub_entry_id = picked
        hub = hub_entry_by_id(self.hass, hub_entry_id) if hub_entry_id else None
        if hub is not None:
            return hub
        hubs = iter_hub_entries(self.hass)
        if len(hubs) == 1:
            return hubs[0]
        return None

    async def _async_ensure_hub_for_remote_flow(
        self, user_input: dict[str, Any] | None
    ) -> config_entries.ConfigEntry | None:
        """Create pending hub config entry when hub+remote are added in one flow."""
        hub = self._async_resolve_hub_for_remote(user_input)
        if hub is not None:
            return hub
        if self._pending_hub_endpoint_id is None or self._hub_ieee is None:
            return None
        hub_entry_id = await self._async_register_hub_config_entry(
            endpoint_id=self._pending_hub_endpoint_id
        )
        self._pending_hub_endpoint_id = None
        self._prefill_hub_entry_id = hub_entry_id
        self.context["hub_entry_id"] = hub_entry_id
        return hub_entry_by_id(self.hass, hub_entry_id)

    async def _async_register_hub_config_entry(self, *, endpoint_id: int) -> str:
        """Register hub config entry while config flow continues (hub+remote session)."""
        ieee = self._hub_ieee
        if ieee is None:
            raise ValueError("hub ieee missing")
        unique_id = ieee.lower().replace(" ", "")
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        title = self._hub_device_name or f"IR Hub {ieee}"
        data: dict[str, Any] = {
            CONF_ENTRY_KIND: ENTRY_KIND_HUB,
            CONF_IEEE: ieee,
            CONF_ENDPOINT_ID: endpoint_id,
            CONF_TRANSPORT: TRANSPORT_TS1201_ZHA,
        }
        entry = config_entries.ConfigEntry(
            version=self.VERSION,
            minor_version=self.MINOR_VERSION,
            domain=DOMAIN,
            title=title,
            data=data,
            source=config_entries.SOURCE_USER,
            unique_id=unique_id,
            discovery_keys=set(),
        )
        created = await self.hass.config_entries.async_add(entry)
        await self.hass.config_entries.async_setup(created.entry_id)
        return created.entry_id

    async def async_step_hub_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add remote to an existing hub (or pending hub in the same flow)."""
        hubs = iter_hub_entries(self.hass)
        pending_hub = self._pending_hub_endpoint_id is not None and self._hub_ieee
        if not hubs and not pending_hub:
            return self.async_abort(reason="hub_not_found")

        hub = await self._async_ensure_hub_for_remote_flow(user_input)
        need_hub_pick = hub is None and len(hubs) > 1

        errors: dict[str, str] = {}
        profile_options = await async_select_selector_options(self.hass)
        default_profile = profile_options[0]["value"] if profile_options else PROFILE_CUSTOM

        if user_input is not None and CONF_HUB_ENTRY_ID in user_input and hub is not None:
            self._prefill_hub_entry_id = hub.entry_id
            self.context["hub_entry_id"] = hub.entry_id

        if (
            user_input is not None
            and not need_hub_pick
            and CONF_PROFILE_CHOICE in user_input
        ):
            hub = await self._async_ensure_hub_for_remote_flow(user_input)
            if hub is None:
                return self.async_abort(reason="hub_not_found")
            profile_choice = user_input.get(CONF_PROFILE_CHOICE, default_profile)
            custom_path = user_input.get(CONF_PROFILE_PATH)
            try:
                resolved_path = resolve_stored_profile_path(
                    str(profile_choice), custom_path
                )
            except ValueError:
                errors["base"] = "invalid_profile"
            else:
                remote_name = str(user_input.get(CONF_REMOTE_NAME, "")).strip() or None
                return await self._async_create_remote_entry(
                    hub_entry_id=hub.entry_id,
                    profile_path=resolved_path,
                    remote_name=remote_name,
                )

        if user_input is not None and CONF_HUB_ENTRY_ID in user_input:
            hub = await self._async_ensure_hub_for_remote_flow(user_input)
            need_hub_pick = False

        schema_fields: dict[vol.Marker, Any] = {}
        if need_hub_pick:
            schema_fields[vol.Required(CONF_HUB_ENTRY_ID)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": h.entry_id, "label": h.title} for h in hubs
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            if hub is None:
                hub = await self._async_ensure_hub_for_remote_flow(user_input)
            if hub is None:
                return self.async_abort(reason="hub_not_found")
            schema_fields[vol.Required(CONF_PROFILE_CHOICE, default=default_profile)] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=profile_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            )
            schema_fields[vol.Optional(CONF_PROFILE_PATH)] = selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT,
                )
            )
            schema_fields[vol.Optional(CONF_REMOTE_NAME)] = selector.TextSelector()

        data_schema = vol.Schema(schema_fields)
        return self.async_show_form(
            step_id="hub_remote",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"hub_title": hub.title if hub else ""},
        )

    def _async_create_hub_entry(
        self, *, endpoint_id: int, offer_remote_setup: bool = False
    ) -> FlowResult:
        """Create hub config entry (end of hub-only flow)."""
        ieee = self._hub_ieee
        if ieee is None:
            raise ValueError("hub ieee missing")
        title = self._hub_device_name or f"IR Hub {ieee}"
        data: dict[str, Any] = {
            CONF_ENTRY_KIND: ENTRY_KIND_HUB,
            CONF_IEEE: ieee,
            CONF_ENDPOINT_ID: endpoint_id,
            CONF_TRANSPORT: TRANSPORT_TS1201_ZHA,
        }
        if offer_remote_setup:
            data["offer_remote_setup"] = True
        return self.async_create_entry(title=title, data=data)

    async def _async_create_remote_entry(
        self,
        *,
        hub_entry_id: str,
        profile_path: str,
        remote_name: str | None,
    ) -> FlowResult:
        """Create remote config entry linked to hub."""
        from pathlib import Path

        slug = Path(profile_path).stem
        unique = f"{hub_entry_id}_{slug}"
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured()

        data: dict[str, Any] = {
            CONF_ENTRY_KIND: ENTRY_KIND_REMOTE,
            CONF_HUB_ENTRY_ID: hub_entry_id,
            CONF_HUB_IDS: [hub_entry_id],
            CONF_PROFILE_PATH: profile_path,
        }
        if remote_name:
            data[CONF_REMOTE_NAME] = remote_name

        return self.async_create_entry(
            title=remote_name or f"Remote {slug}",
            data=data,
        )


class EasyIrOptionsFlowHandler(config_entries.OptionsFlow):
    """Options for an existing hub entry."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def _async_option_label(self, option_key: str) -> str:
        from homeassistant.helpers import translation

        strings = await translation.async_get_translations(
            self.hass,
            self.hass.config.language,
            "config",
            integrations=[DOMAIN],
        )
        return strings.get(
            f"component.{DOMAIN}.config.step.menu.menu_options.{option_key}",
            option_key,
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not is_hub_entry(self._entry):
            return self.async_abort(reason="not_hub_entry")
        return await self.async_step_menu()

    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            add_remote_label = await self._async_option_label(FLOW_SOURCE_ADD_REMOTE)
            add_hub_label = await self._async_option_label(FLOW_SOURCE_ADD_HUB)
            return self.async_show_menu(
                step_id="menu",
                menu_options={
                    FLOW_SOURCE_ADD_REMOTE: add_remote_label,
                    FLOW_SOURCE_ADD_HUB: add_hub_label,
                },
            )
        if user_input == FLOW_SOURCE_ADD_REMOTE:
            return await self.async_step_add_remote()
        if user_input == FLOW_SOURCE_ADD_HUB:
            return await self.async_step_add_hub()
        return self.async_create_entry(title="", data={})

    async def async_step_add_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        await self.hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": FLOW_SOURCE_HUB_REMOTE,
                "hub_entry_id": self._entry.entry_id,
            },
        )
        return self.async_create_entry(title="", data={})

    async def async_step_add_hub(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        await self.hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": FLOW_SOURCE_ADD_HUB},
        )
        return self.async_create_entry(title="", data={})


def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> EasyIrOptionsFlowHandler:
    return EasyIrOptionsFlowHandler(config_entry)
