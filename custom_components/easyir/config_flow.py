"""Config flow for EasyIR (single parent entry + hub/remote subentries)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
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
    DEFAULT_ENDPOINT_ID,
    DOMAIN,
    PARENT_ENTRY_UNIQUE_ID,
    SUBENTRY_TYPE_HUB,
    SUBENTRY_TYPE_REMOTE,
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
CONF_REMOTE_TYPE = "remote_type"
CONF_REMOTE_BRAND = "remote_brand"
REMOTE_TYPE_CLIMATE = "climate"
REMOTE_TYPE_ADVANCED = "advanced"


def _ieee_from_zha_device(device: dr.DeviceEntry) -> str | None:
    return ieee_from_zha_device(device)


def _area_id_from_input(user_input: dict[str, Any]) -> str | None:
    area_id = user_input.get(CONF_AREA_ID)
    if area_id is None:
        return None
    area_str = str(area_id).strip()
    return area_str or None


def _default_name_for_device(device: dr.DeviceEntry | None, ieee: str | None = None) -> str:
    if device is not None:
        return device.name_by_user or device.name or ""
    if ieee:
        return f"IR Hub {ieee}"
    return "IR Hub"


def _combined_hub_pick_schema(
    *,
    discovered: list[tuple[str, str]],
    manual_label: str,
    default_pick: str | None = None,
    default_name: str = "",
) -> vol.Schema:
    """One form: hub + name + room."""
    select_options = [{"value": dev_id, "label": label} for dev_id, label in discovered]
    select_options.append({"value": MENU_MANUAL, "label": manual_label})
    pick_default = default_pick or (discovered[0][0] if len(discovered) == 1 else None)
    fields: dict[vol.Marker, Any] = {
        vol.Required(CONF_HUB_NAME, default=default_name): selector.TextSelector(),
        vol.Optional(CONF_AREA_ID): selector.AreaSelector(),
    }
    if pick_default is not None:
        fields[vol.Required(CONF_HUB_PICK, default=pick_default)] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=select_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
    else:
        fields[vol.Required(CONF_HUB_PICK)] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=select_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
    return vol.Schema(fields)


def _manual_hub_schema(*, default_name: str = "") -> vol.Schema:
    return vol.Schema(
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
            vol.Required(CONF_HUB_NAME, default=default_name): selector.TextSelector(),
            vol.Optional(CONF_AREA_ID): selector.AreaSelector(),
        }
    )


def _split_brand_model(label: str) -> tuple[str, str]:
    """Split profile title into brand/model parts for remote wizard."""
    normalized = str(label).strip()
    if not normalized:
        return "Other", "Unknown model"
    if "—" in normalized:
        left, right = normalized.split("—", 1)
        brand = left.strip() or "Other"
        model = right.strip() or "Unknown model"
        return brand, model
    if "-" in normalized:
        left, right = normalized.split("-", 1)
        brand = left.strip() or "Other"
        model = right.strip() or "Unknown model"
        return brand, model
    return "Other", normalized


def _climate_catalog_from_options(
    profile_options: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Build brand -> model selector options from bundled climate entries."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for option in profile_options:
        value = str(option.get("value", "")).strip()
        if not (value.startswith("climate/") and value.endswith(".json")):
            continue
        label = str(option.get("label", value)).strip()
        brand, model = _split_brand_model(label)
        grouped[brand].append(
            {
                "value": value,
                "label": model,
            }
        )
    catalog: dict[str, list[dict[str, str]]] = {}
    for brand in sorted(grouped, key=lambda item: item.lower()):
        models = sorted(grouped[brand], key=lambda item: item["label"].lower())
        catalog[brand] = models
    return catalog


def _resolve_hub_from_device(
    hass: Any, device: dr.DeviceEntry
) -> tuple[str, str, int] | None:
    ieee = _ieee_from_zha_device(device)
    if ieee is None:
        return None
    name = _default_name_for_device(device, ieee)
    endpoint_id = endpoint_for_zha_device(device)
    return ieee, name, endpoint_id


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
        """First-time setup from discovered TS1201 — one step (name + room)."""
        device_id = str(discovery_info.get("device_id", "")).strip()
        ieee = str(discovery_info.get("ieee", "")).strip() or None
        device_reg = dr.async_get(self.hass)
        device = device_reg.async_get(device_id) if device_id else None
        if device is not None:
            ieee = ieee or _ieee_from_zha_device(device)
            self._hub_device_name = _default_name_for_device(device, ieee)
        if ieee is None:
            return self.async_abort(reason="unknown_ieee")
        self._hub_ieee = ieee
        self._hub_endpoint_id = endpoint_for_ieee(self.hass, ieee)
        return await self.async_step_user(user_input=None, from_discovery=True)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
        from_discovery: bool = False,
    ) -> FlowResult:
        """First integration setup: hub + name + room in one step."""
        if self.hass.config_entries.async_entries(DOMAIN):
            return self.async_abort(reason="already_configured")
        if not self.hass.config_entries.async_entries(ZHA_DOMAIN):
            return self.async_abort(reason="zha_not_configured")

        if self._hub_ieee is not None:
            default_name = self._hub_device_name or f"IR Hub {self._hub_ieee}"
            if user_input is not None:
                return await self._async_create_parent_with_hub(
                    ieee=self._hub_ieee,
                    endpoint_id=self._hub_endpoint_id,
                    hub_name=str(user_input.get(CONF_HUB_NAME, "")).strip() or default_name,
                    area_id=_area_id_from_input(user_input),
                )
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_HUB_NAME, default=default_name): selector.TextSelector(),
                        vol.Optional(CONF_AREA_ID): selector.AreaSelector(),
                    }
                ),
                description_placeholders={"hub_name": default_name},
            )

        return await self._async_step_combined_hub(user_input)

    async def async_step_pick_hub(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self._async_step_combined_hub(user_input)

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
                resolved = _resolve_hub_from_device(self.hass, device)
                if resolved is None:
                    errors["base"] = "unknown_ieee"
                else:
                    ieee, default_name, endpoint_id = resolved
                    await self.async_set_unique_id(ieee.lower().replace(" ", ""))
                    self._abort_if_unique_id_configured()
                    hub_name = str(user_input.get(CONF_HUB_NAME, "")).strip() or default_name
                    return await self._async_create_parent_with_hub(
                        ieee=ieee,
                        endpoint_id=endpoint_id,
                        hub_name=hub_name,
                        area_id=_area_id_from_input(user_input),
                    )

        return self.async_show_form(
            step_id="hub_manual",
            data_schema=_manual_hub_schema(),
            errors=errors,
        )

    async def _async_step_combined_hub(
        self, user_input: dict[str, Any] | None
    ) -> FlowResult:
        discovered = list_onboarding_hub_choices(self.hass)
        if not discovered:
            return await self.async_step_hub_manual(user_input)

        if user_input is not None:
            pick = str(user_input.get(CONF_HUB_PICK, "")).strip()
            if pick == MENU_MANUAL:
                return await self.async_step_hub_manual()
            device_reg = dr.async_get(self.hass)
            device = device_reg.async_get(pick)
            if device is None:
                return self.async_abort(reason="invalid_device")
            resolved = _resolve_hub_from_device(self.hass, device)
            if resolved is None:
                return self.async_abort(reason="unknown_ieee")
            ieee, default_name, endpoint_id = resolved
            await self.async_set_unique_id(ieee.lower().replace(" ", ""))
            self._abort_if_unique_id_configured()
            hub_name = str(user_input.get(CONF_HUB_NAME, "")).strip() or default_name
            return await self._async_create_parent_with_hub(
                ieee=ieee,
                endpoint_id=endpoint_id,
                hub_name=hub_name,
                area_id=_area_id_from_input(user_input),
            )

        manual_label = await self._async_manual_hub_pick_label()
        default_pick = discovered[0][0] if len(discovered) == 1 else None
        default_name = ""
        if default_pick:
            device = dr.async_get(self.hass).async_get(default_pick)
            default_name = _default_name_for_device(device)
        return self.async_show_form(
            step_id="user",
            data_schema=_combined_hub_pick_schema(
                discovered=discovered,
                manual_label=manual_label,
                default_pick=default_pick,
                default_name=default_name,
            ),
            description_placeholders={"count": str(len(discovered))},
        )

    async def _async_create_parent_with_hub(
        self,
        *,
        ieee: str,
        endpoint_id: int,
        hub_name: str,
        area_id: str | None,
    ) -> FlowResult:
        ieee_norm = ieee.lower().replace(" ", "")
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
                        ieee=ieee,
                        endpoint_id=endpoint_id,
                        area_id=area_id,
                    ),
                }
            ],
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

    async def _async_create_hub_subentry(
        self,
        *,
        ieee: str,
        endpoint_id: int,
        hub_name: str,
        area_id: str | None,
    ) -> FlowResult:
        return self.async_create_entry(  # type: ignore[attr-defined]
            title=hub_name,
            data=hub_subentry_data(
                ieee=ieee,
                endpoint_id=endpoint_id,
                area_id=area_id,
            ),
            unique_id=ieee.lower().replace(" ", ""),
        )

    async def _async_step_combined_hub_subentry(
        self, user_input: dict[str, Any] | None
    ) -> FlowResult:
        discovered = list_onboarding_hub_choices(self.hass)
        if not discovered:
            return self.async_abort(  # type: ignore[attr-defined]
                reason="all_supported_hubs_added"
            )

        if user_input is not None:
            pick = str(user_input.get(CONF_HUB_PICK, "")).strip()
            if pick == MENU_MANUAL:
                return await self.async_step_hub_manual()  # type: ignore[attr-defined]
            device_reg = dr.async_get(self.hass)
            device = device_reg.async_get(pick)
            if device is None:
                return self.async_abort(reason="invalid_device")  # type: ignore[attr-defined]
            resolved = _resolve_hub_from_device(self.hass, device)
            if resolved is None:
                return self.async_abort(reason="unknown_ieee")  # type: ignore[attr-defined]
            ieee, default_name, endpoint_id = resolved
            await self.async_set_unique_id(ieee.lower().replace(" ", ""))  # type: ignore[attr-defined]
            self._abort_if_unique_id_configured()  # type: ignore[attr-defined]
            hub_name = str(user_input.get(CONF_HUB_NAME, "")).strip() or default_name
            return await self._async_create_hub_subentry(
                ieee=ieee,
                endpoint_id=endpoint_id,
                hub_name=hub_name,
                area_id=_area_id_from_input(user_input),
            )

        manual_label = await self._async_manual_hub_pick_label()
        default_pick = discovered[0][0] if len(discovered) == 1 else None
        default_name = ""
        if default_pick:
            device = dr.async_get(self.hass).async_get(default_pick)
            default_name = _default_name_for_device(device)
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="user",
            data_schema=_combined_hub_pick_schema(
                discovered=discovered,
                manual_label=manual_label,
                default_pick=default_pick,
                default_name=default_name,
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
        if init and self._hub_ieee is None and user_input is None:
            device_id = str(init.get("device_id", "")).strip()
            ieee = str(init.get("ieee", "")).strip() or None
            device_reg = dr.async_get(self.hass)
            device = device_reg.async_get(device_id) if device_id else None
            if device is not None:
                ieee = ieee or _ieee_from_zha_device(device)
                self._hub_device_name = _default_name_for_device(device, ieee)
            if ieee:
                self._hub_ieee = ieee
                self._hub_endpoint_id = endpoint_for_ieee(self.hass, ieee)

        if self._hub_ieee is not None:
            default_name = self._hub_device_name or f"IR Hub {self._hub_ieee}"
            if user_input is not None:
                await self.async_set_unique_id(self._hub_ieee.lower().replace(" ", ""))
                self._abort_if_unique_id_configured()
                hub_name = str(user_input.get(CONF_HUB_NAME, "")).strip() or default_name
                return await self._async_create_hub_subentry(
                    ieee=self._hub_ieee,
                    endpoint_id=self._hub_endpoint_id,
                    hub_name=hub_name,
                    area_id=_area_id_from_input(user_input),
                )
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_HUB_NAME, default=default_name): selector.TextSelector(),
                        vol.Optional(CONF_AREA_ID): selector.AreaSelector(),
                    }
                ),
                description_placeholders={"hub_name": default_name},
            )

        return await self._async_step_combined_hub_subentry(user_input)

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
                resolved = _resolve_hub_from_device(self.hass, device)
                if resolved is None:
                    errors["base"] = "unknown_ieee"
                else:
                    ieee, default_name, endpoint_id = resolved
                    await self.async_set_unique_id(ieee.lower().replace(" ", ""))
                    self._abort_if_unique_id_configured()
                    hub_name = str(user_input.get(CONF_HUB_NAME, "")).strip() or default_name
                    return await self._async_create_hub_subentry(
                        ieee=ieee,
                        endpoint_id=endpoint_id,
                        hub_name=hub_name,
                        area_id=_area_id_from_input(user_input),
                    )

        return self.async_show_form(
            step_id="hub_manual",
            data_schema=_manual_hub_schema(),
            errors=errors,
        )


class IrRemoteSubentryFlow(ConfigSubentryFlow):
    """Add a virtual IR remote from the EasyIR integration card."""

    def __init__(self) -> None:
        self._prefill_hub_id: str | None = None
        self._selected_hub_id: str | None = None
        self._selected_remote_type: str | None = None
        self._selected_brand: str | None = None
        self._profile_options_cache: list[dict[str, str]] | None = None

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
            self._selected_hub_id = prefill

        errors: dict[str, str] = {}
        if user_input is not None:
            if CONF_HUB_SUBENTRY_ID in user_input:
                self._selected_hub_id = str(user_input[CONF_HUB_SUBENTRY_ID]).strip()
            elif CONF_HUB_ENTRY_ID in user_input:
                self._selected_hub_id = str(user_input[CONF_HUB_ENTRY_ID]).strip()
            elif self._prefill_hub_id:
                self._selected_hub_id = self._prefill_hub_id

            if not self._selected_hub_id or hub_ref_by_id(self.hass, self._selected_hub_id) is None:
                errors["base"] = "hub_not_found"
            else:
                return await self.async_step_remote_type()

        if self._selected_hub_id is None and len(hubs) == 1:
            self._selected_hub_id = hubs[0].subentry_id

        if self._selected_hub_id and hub_ref_by_id(self.hass, self._selected_hub_id):
            return await self.async_step_remote_type()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HUB_SUBENTRY_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": h.subentry_id, "label": h.title} for h in hubs
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_remote_type(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        hub_id = self._selected_hub_id or self._prefill_hub_id
        if not hub_id:
            return self.async_abort(reason="hub_not_found")
        hub = hub_ref_by_id(self.hass, hub_id)
        if hub is None:
            return self.async_abort(reason="hub_not_found")
        self._selected_hub_id = hub_id

        profile_options = await self._async_profile_options()
        catalog = _climate_catalog_from_options(profile_options)
        selector_options: list[dict[str, str]] = []
        if catalog:
            selector_options.append(
                {"value": REMOTE_TYPE_CLIMATE, "label": "Кондиционер / климат"}
            )
        selector_options.append(
            {
                "value": REMOTE_TYPE_ADVANCED,
                "label": "Продвинутый выбор профиля",
            }
        )
        default_type = (
            self._selected_remote_type
            or (REMOTE_TYPE_CLIMATE if catalog else REMOTE_TYPE_ADVANCED)
        )
        available_values = {item["value"] for item in selector_options}
        if default_type not in available_values:
            default_type = selector_options[0]["value"]
        errors: dict[str, str] = {}
        if user_input is not None:
            remote_type = str(user_input.get(CONF_REMOTE_TYPE, "")).strip()
            if remote_type not in available_values:
                errors["base"] = "invalid_remote_type"
            else:
                self._selected_remote_type = remote_type
                self._selected_brand = None
                if remote_type == REMOTE_TYPE_CLIMATE:
                    return await self.async_step_remote_brand()
                return await self.async_step_hub_remote()

        return self.async_show_form(
            step_id="remote_type",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REMOTE_TYPE, default=default_type): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=selector_options,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={"hub_title": hub.title},
        )

    async def async_step_remote_brand(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        hub_id = self._selected_hub_id or self._prefill_hub_id
        hub = hub_ref_by_id(self.hass, hub_id or "")
        if hub is None:
            return self.async_abort(reason="hub_not_found")
        self._selected_hub_id = hub.subentry_id

        profile_options = await self._async_profile_options()
        catalog = _climate_catalog_from_options(profile_options)
        if not catalog:
            return self.async_abort(reason="no_climate_profiles")

        brands = sorted(catalog.keys(), key=lambda item: item.lower())
        default_brand = self._selected_brand or brands[0]
        errors: dict[str, str] = {}
        if user_input is not None:
            brand = str(user_input.get(CONF_REMOTE_BRAND, "")).strip()
            if brand not in catalog:
                errors["base"] = "invalid_profile"
            else:
                self._selected_brand = brand
                return await self.async_step_hub_remote()

        return self.async_show_form(
            step_id="remote_brand",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REMOTE_BRAND, default=default_brand): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": brand, "label": brand} for brand in brands
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={"hub_title": hub.title},
        )

    async def async_step_hub_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Final step: pick concrete profile and create remote subentry."""
        hub_id = self._selected_hub_id or self._prefill_hub_id
        if not hub_id:
            return self.async_abort(reason="hub_not_found")
        hub = hub_ref_by_id(self.hass, hub_id)
        if hub is None:
            return self.async_abort(reason="hub_not_found")
        self._selected_hub_id = hub.subentry_id

        profile_options = await self._async_profile_options()
        catalog = _climate_catalog_from_options(profile_options)
        default_profile = profile_options[0]["value"] if profile_options else PROFILE_CUSTOM
        errors: dict[str, str] = {}
        brand_placeholder = ""

        if self._selected_remote_type == REMOTE_TYPE_CLIMATE:
            if not catalog:
                return self.async_abort(reason="no_climate_profiles")
            brand = self._selected_brand or next(iter(catalog))
            models = catalog.get(brand)
            if not models:
                return self.async_abort(reason="invalid_profile")
            brand_placeholder = brand
            model_values = {item["value"] for item in models}
            model_default = models[0]["value"]
            if user_input is not None:
                profile_choice = str(
                    user_input.get(CONF_PROFILE_CHOICE, model_default)
                ).strip()
                if profile_choice not in model_values:
                    errors["base"] = "invalid_profile"
                else:
                    remote_name = str(user_input.get(CONF_REMOTE_NAME, "")).strip() or None
                    resolved_path = resolve_stored_profile_path(profile_choice, None)
                    return await self._async_create_remote_subentry(
                        hub_id=hub.subentry_id,
                        profile_path=resolved_path,
                        remote_name=remote_name,
                    )

            return self.async_show_form(
                step_id="hub_remote",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_PROFILE_CHOICE, default=model_default): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=models,
                                mode=selector.SelectSelectorMode.LIST,
                            )
                        ),
                        vol.Optional(CONF_REMOTE_NAME): selector.TextSelector(),
                    }
                ),
                errors=errors,
                description_placeholders={
                    "hub_title": hub.title,
                    "remote_brand": brand_placeholder,
                },
            )

        # Advanced path: full selector + optional custom profile path.
        if user_input is not None:
            profile_choice = str(user_input.get(CONF_PROFILE_CHOICE, default_profile))
            custom_path = user_input.get(CONF_PROFILE_PATH)
            try:
                resolved_path = resolve_stored_profile_path(profile_choice, custom_path)
            except ValueError:
                errors["base"] = "invalid_profile"
            else:
                remote_name = str(user_input.get(CONF_REMOTE_NAME, "")).strip() or None
                return await self._async_create_remote_subentry(
                    hub_id=hub.subentry_id,
                    profile_path=resolved_path,
                    remote_name=remote_name,
                )

        return self.async_show_form(
            step_id="hub_remote",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROFILE_CHOICE, default=default_profile): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=profile_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_PROFILE_PATH): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Optional(CONF_REMOTE_NAME): selector.TextSelector(),
                }
            ),
            errors=errors,
            description_placeholders={
                "hub_title": hub.title,
                "remote_brand": brand_placeholder,
            },
        )

    async def _async_profile_options(self) -> list[dict[str, str]]:
        if self._profile_options_cache is not None:
            return list(self._profile_options_cache)
        self._profile_options_cache = await async_select_selector_options(self.hass)
        return list(self._profile_options_cache)

    async def _async_create_remote_subentry(
        self,
        *,
        hub_id: str,
        profile_path: str,
        remote_name: str | None,
    ) -> FlowResult:
        slug = Path(profile_path).stem
        unique = f"{hub_id}_{slug}"
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=remote_name or f"Remote {slug}",
            data=remote_subentry_data(
                hub_subentry_id=hub_id,
                profile_path=profile_path,
                remote_name=remote_name,
            ),
            unique_id=unique,
        )
