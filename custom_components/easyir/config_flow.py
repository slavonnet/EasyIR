"""Config flow for EasyIR (single parent entry + hub/remote subentries)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigSubentryFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .bundled_profiles import (
    PROFILE_CUSTOM,
    async_select_selector_options,
    resolve_stored_profile_path,
)
from .const import (
    CONF_AREA_ID,
    CONF_ENDPOINT_ID,
    CONF_HUB_ENTRY_ID,
    CONF_HUB_NAME,
    CONF_HUB_SUBENTRY_ID,
    CONF_IEEE,
    CONF_PROFILE_CHOICE,
    CONF_PROFILE_PATH,
    CONF_REMOTE_NAME,
    CONF_TRANSPORT,
    DEFAULT_ENDPOINT_ID,
    DOMAIN,
    PARENT_ENTRY_UNIQUE_ID,
    SUBENTRY_TYPE_HUB,
    SUBENTRY_TYPE_REMOTE,
    TRANSPORT_TS1201_ZHA,
    ZHA_DOMAIN,
)
from .endpoint import endpoint_for_ieee, endpoint_for_zha_device
from .hub_registry import (
    hub_ref_by_id,
    hub_subentry_data,
    iter_hub_refs,
    remote_subentry_data,
)
from .supported_hubs import ieee_from_zha_device, list_onboarding_hub_choices

CONF_HUB_PICK = "hub_pick"
CONF_ZHA_DEVICE = "zha_device"
MENU_MANUAL = "manual"


def _ieee_from_zha_device(device: dr.DeviceEntry) -> str | None:
    return ieee_from_zha_device(device)


class EasyIrConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the single EasyIR parent entry and first hub subentry."""

    VERSION = 4
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._hub_ieee: str | None = None
        self._hub_device_name: str | None = None
        self._hub_endpoint_id: int = DEFAULT_ENDPOINT_ID

    @classmethod
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentry flows shown as Add hub / Add remote on the integration card."""
        return {
            SUBENTRY_TYPE_HUB: IrHubSubentryFlow,
            SUBENTRY_TYPE_REMOTE: IrRemoteSubentryFlow,
        }

    async def async_step_import(self, user_input: dict[str, Any]) -> FlowResult:
        """Import remote during legacy migration (v3 only)."""
        return self.async_abort(reason="invalid_import")

    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> FlowResult:
        """First-time setup from discovered TS1201."""
        return await self._async_begin_hub_from_discovery(discovery_info)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """First integration setup: hub + room + name, then EasyIR page."""
        if self.hass.config_entries.async_entries(DOMAIN):
            return self.async_abort(reason="already_configured")
        if not self.hass.config_entries.async_entries(ZHA_DOMAIN):
            return self.async_abort(reason="zha_not_configured")
        if user_input is not None and CONF_HUB_PICK in user_input:
            return await self._async_step_pick_hub(user_input)
        return await self._async_step_pick_hub(user_input)

    async def async_step_pick_hub(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self._async_step_pick_hub(user_input)

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
        self._hub_endpoint_id = endpoint_for_ieee(self.hass, ieee)
        await self.async_set_unique_id(ieee.lower().replace(" ", ""))
        self._abort_if_unique_id_configured()
        return await self.async_step_hub_setup()

    async def _async_step_pick_hub(
        self, user_input: dict[str, Any] | None
    ) -> FlowResult:
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
            self._hub_endpoint_id = endpoint_for_zha_device(device)
            await self.async_set_unique_id(ieee.lower().replace(" ", ""))
            self._abort_if_unique_id_configured()
            return await self.async_step_hub_setup()

        manual_label = await self._async_manual_hub_pick_label()
        select_options = [
            {"value": dev_id, "label": label} for dev_id, label in discovered
        ]
        select_options.append({"value": MENU_MANUAL, "label": manual_label})
        return self.async_show_form(
            step_id="pick_hub",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HUB_PICK): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=select_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders={"count": str(len(discovered))},
        )

    async def async_step_hub_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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
                    self._hub_endpoint_id = endpoint_for_zha_device(device)
                    await self.async_set_unique_id(ieee.lower().replace(" ", ""))
                    self._abort_if_unique_id_configured()
                    return await self.async_step_hub_setup()

        return self.async_show_form(
            step_id="hub_manual",
            data_schema=vol.Schema(
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
            ),
            errors=errors,
        )

    async def async_step_hub_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Hub name and room in one step; creates parent + first hub subentry."""
        if self._hub_ieee is None:
            return self.async_abort(reason="unknown_ieee")

        default_name = self._hub_device_name or f"IR Hub {self._hub_ieee}"
        if user_input is not None:
            hub_name = str(user_input.get(CONF_HUB_NAME, "")).strip() or default_name
            area_id = user_input.get(CONF_AREA_ID)
            area_str = str(area_id).strip() if area_id else None
            ieee_norm = self._hub_ieee.lower().replace(" ", "")
            await self.async_set_unique_id(PARENT_ENTRY_UNIQUE_ID)
            return self.async_create_entry(
                title="EasyIR",
                data={},
                subentries=[
                    {
                        "subentry_type": SUBENTRY_TYPE_HUB,
                        "title": hub_name,
                        "unique_id": ieee_norm,
                        "data": hub_subentry_data(
                            ieee=self._hub_ieee,
                            endpoint_id=self._hub_endpoint_id,
                            area_id=area_str,
                        ),
                    }
                ],
            )

        return self.async_show_form(
            step_id="hub_setup",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HUB_NAME, default=default_name): selector.TextSelector(),
                    vol.Optional(CONF_AREA_ID): selector.AreaSelector(),
                }
            ),
            description_placeholders={"hub_name": default_name},
        )

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


class _HubPickMixin:
    """Shared TS1201 hub selection for subentry flows."""

    hass: Any
    _hub_ieee: str | None
    _hub_device_name: str | None
    _hub_endpoint_id: int

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

    async def _async_step_pick_hub_subentry(
        self, user_input: dict[str, Any] | None
    ) -> FlowResult:
        discovered = list_onboarding_hub_choices(self.hass)
        if not discovered:
            return await self.async_step_hub_manual()  # type: ignore[attr-defined]

        if user_input is not None:
            pick = str(user_input.get(CONF_HUB_PICK, "")).strip()
            if pick == MENU_MANUAL:
                return await self.async_step_hub_manual()  # type: ignore[attr-defined]
            device_reg = dr.async_get(self.hass)
            device = device_reg.async_get(pick)
            if device is None:
                return self.async_abort(reason="invalid_device")  # type: ignore[attr-defined]
            ieee = _ieee_from_zha_device(device)
            if ieee is None:
                return self.async_abort(reason="unknown_ieee")  # type: ignore[attr-defined]
            self._hub_ieee = ieee
            self._hub_device_name = device.name_by_user or device.name
            self._hub_endpoint_id = endpoint_for_zha_device(device)
            await self.async_set_unique_id(ieee.lower().replace(" ", ""))  # type: ignore[attr-defined]
            self._abort_if_unique_id_configured()  # type: ignore[attr-defined]
            return await self.async_step_hub_setup()  # type: ignore[attr-defined]

        manual_label = await self._async_manual_hub_pick_label()
        select_options = [
            {"value": dev_id, "label": label} for dev_id, label in discovered
        ]
        select_options.append({"value": MENU_MANUAL, "label": manual_label})
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="pick_hub",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HUB_PICK): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=select_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders={"count": str(len(discovered))},
        )


class IrHubSubentryFlow(_HubPickMixin, ConfigSubentryFlow):
    """Add another IR hub from the EasyIR integration card."""

    def __init__(self) -> None:
        self._hub_ieee = None
        self._hub_device_name = None
        self._hub_endpoint_id = DEFAULT_ENDPOINT_ID

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not self.hass.config_entries.async_entries(ZHA_DOMAIN):
            return self.async_abort(reason="zha_not_configured")
        init = self.context.get("discovery_info") or {}
        if init and self._hub_ieee is None:
            device_id = str(init.get("device_id", "")).strip()
            ieee = str(init.get("ieee", "")).strip() or None
            device_reg = dr.async_get(self.hass)
            if device_id:
                device = device_reg.async_get(device_id)
                if device is not None:
                    ieee = ieee or _ieee_from_zha_device(device)
                    self._hub_device_name = device.name_by_user or device.name
            if ieee:
                self._hub_ieee = ieee
                self._hub_endpoint_id = endpoint_for_ieee(self.hass, ieee)
                await self.async_set_unique_id(ieee.lower().replace(" ", ""))
                self._abort_if_unique_id_configured()
                return await self.async_step_hub_setup()
        if user_input is not None and CONF_HUB_PICK in user_input:
            return await self._async_step_pick_hub_subentry(user_input)
        return await self._async_step_pick_hub_subentry(user_input)

    async def async_step_pick_hub(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self._async_step_pick_hub_subentry(user_input)

    async def async_step_hub_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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
                    self._hub_endpoint_id = endpoint_for_zha_device(device)
                    await self.async_set_unique_id(ieee.lower().replace(" ", ""))
                    self._abort_if_unique_id_configured()
                    return await self.async_step_hub_setup()

        return self.async_show_form(
            step_id="hub_manual",
            data_schema=vol.Schema(
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
            ),
            errors=errors,
        )

    async def async_step_hub_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if self._hub_ieee is None:
            return self.async_abort(reason="unknown_ieee")

        default_name = self._hub_device_name or f"IR Hub {self._hub_ieee}"
        if user_input is not None:
            hub_name = str(user_input.get(CONF_HUB_NAME, "")).strip() or default_name
            area_id = user_input.get(CONF_AREA_ID)
            area_str = str(area_id).strip() if area_id else None
            return self.async_create_entry(
                title=hub_name,
                data=hub_subentry_data(
                    ieee=self._hub_ieee,
                    endpoint_id=self._hub_endpoint_id,
                    area_id=area_str,
                ),
                unique_id=self._hub_ieee.lower().replace(" ", ""),
            )

        return self.async_show_form(
            step_id="hub_setup",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HUB_NAME, default=default_name): selector.TextSelector(),
                    vol.Optional(CONF_AREA_ID): selector.AreaSelector(),
                }
            ),
            description_placeholders={"hub_name": default_name},
        )


class IrRemoteSubentryFlow(ConfigSubentryFlow):
    """Add a virtual IR remote from the EasyIR integration card."""

    def __init__(self) -> None:
        self._prefill_hub_id: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        parent = self._get_entry()
        hubs = iter_hub_refs(self.hass, parent)
        if not hubs:
            return self.async_abort(reason="hub_not_found")

        prefill = str(self.context.get("hub_subentry_id", "")).strip()
        if prefill:
            self._prefill_hub_id = prefill

        errors: dict[str, str] = {}
        profile_options = await async_select_selector_options(self.hass)
        default_profile = profile_options[0]["value"] if profile_options else PROFILE_CUSTOM

        hub_id = self._prefill_hub_id
        if user_input is not None:
            if CONF_HUB_SUBENTRY_ID in user_input:
                hub_id = str(user_input[CONF_HUB_SUBENTRY_ID]).strip()
            elif CONF_HUB_ENTRY_ID in user_input:
                hub_id = str(user_input[CONF_HUB_ENTRY_ID]).strip()

        if user_input is not None and CONF_PROFILE_CHOICE in user_input:
            hub_id = hub_id or self._prefill_hub_id
            if not hub_id or hub_ref_by_id(self.hass, hub_id) is None:
                errors["base"] = "hub_not_found"
            else:
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
                    from pathlib import Path

                    slug = Path(resolved_path).stem
                    unique = f"{hub_id}_{slug}"
                    await self.async_set_unique_id(unique)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=remote_name or f"Remote {slug}",
                        data=remote_subentry_data(
                            hub_subentry_id=hub_id,
                            profile_path=resolved_path,
                            remote_name=remote_name,
                        ),
                        unique_id=unique,
                    )

        need_hub_pick = hub_id is None and len(hubs) > 1
        schema_fields: dict[vol.Marker, Any] = {}
        if need_hub_pick:
            schema_fields[vol.Required(CONF_HUB_SUBENTRY_ID)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": h.subentry_id, "label": h.title} for h in hubs
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            resolved_hub = hub_id or hubs[0].subentry_id
            hub = hub_ref_by_id(self.hass, resolved_hub)
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
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            )
            schema_fields[vol.Optional(CONF_REMOTE_NAME)] = selector.TextSelector()

        return self.async_show_form(
            step_id="hub_remote",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders={
                "hub_title": hub_ref_by_id(self.hass, hub_id or hubs[0].subentry_id).title
                if hub_ref_by_id(self.hass, hub_id or hubs[0].subentry_id)
                else ""
            },
        )
