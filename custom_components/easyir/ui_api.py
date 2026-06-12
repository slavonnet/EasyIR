"""HTTP API for EasyIR main UI panel (tree + wizard flows)."""

from __future__ import annotations

from http import HTTPStatus
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from aiohttp import web
import voluptuous as vol

from homeassistant.components import http
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr

from .bundled_profiles import async_select_selector_options, resolve_stored_profile_path
from .const import (
    CONF_AREA_ID,
    CONF_ENDPOINT_ID,
    CONF_IEEE,
    CONF_PROFILE_PATH,
    CONF_REMOTE_NAME,
    DOMAIN,
    SUBENTRY_TYPE_HUB,
    SUBENTRY_TYPE_REMOTE,
)
from .endpoint import endpoint_for_zha_device
from .hub_registry import (
    configured_hub_ieees,
    hub_ids_for_remote_data,
    hub_ref_by_id,
    hub_subentry_data,
    iter_hub_refs,
    iter_remote_refs,
    parent_entry,
    remote_display_name,
    remote_subentry_data,
)
from .remote_catalog import (
    REMOTE_TYPE_CLIMATE,
    REMOTE_TYPE_OTHER,
    REMOTE_TYPE_TV,
    catalog_for_remote_type,
)
from .supported_hubs import ieee_from_zha_device, list_onboarding_hub_choices

REMOTE_TYPE_SCHEMA = vol.In({REMOTE_TYPE_CLIMATE, REMOTE_TYPE_TV, REMOTE_TYPE_OTHER})

CREATE_REMOTE_SCHEMA = vol.Schema(
    {
        vol.Required("hub_id"): vol.All(str, vol.Length(min=1)),
        vol.Required("remote_type"): REMOTE_TYPE_SCHEMA,
        vol.Required("profile_choice"): vol.All(str, vol.Length(min=1)),
        vol.Optional("brand"): str,
        vol.Optional(CONF_REMOTE_NAME): str,
        vol.Optional(CONF_PROFILE_PATH): str,
    }
)

CREATE_HUB_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): vol.All(str, vol.Length(min=1)),
        vol.Required("hub_name"): vol.All(str, vol.Length(min=1)),
        vol.Optional(CONF_AREA_ID): str,
    }
)


def _normalize_ieee(value: str) -> str:
    return value.lower().replace(" ", "")


def _next_remote_unique_id(
    entry: Any, *, hub_id: str, profile_path: str
) -> tuple[str, str]:
    from pathlib import Path

    slug = Path(profile_path).stem
    base = f"{hub_id}_{slug}"
    existing = {
        str(sub.unique_id)
        for sub in entry.subentries.values()
        if sub.subentry_type == SUBENTRY_TYPE_REMOTE and sub.unique_id
    }
    if base not in existing:
        return base, slug
    index = 2
    while f"{base}_{index}" in existing:
        index += 1
    return f"{base}_{index}", slug


async def _async_reload_parent(hass: HomeAssistant, entry_id: str) -> None:
    await hass.config_entries.async_reload(entry_id)


class EasyIrUiStateView(http.HomeAssistantView):
    """Return hubs/remotes tree for EasyIR panel."""

    url = "/api/easyir/ui/state"
    name = "api:easyir:ui:state"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[http.KEY_HASS]
        parent = parent_entry(hass)
        if parent is None:
            return self.json({"configured": False, "hubs": []})

        hubs_payload: list[dict[str, Any]] = []
        remotes = iter_remote_refs(hass, parent)
        for hub in iter_hub_refs(hass, parent):
            hub_id = hub.subentry_id
            hub_remotes = []
            for remote in remotes:
                hub_ids = hub_ids_for_remote_data(remote.data)
                if hub_id not in [str(x) for x in hub_ids if x]:
                    continue
                hub_remotes.append(
                    {
                        "remote_id": remote.subentry_id,
                        "title": remote_display_name(remote),
                        "profile_path": str(remote.data.get(CONF_PROFILE_PATH, "")),
                    }
                )
            hubs_payload.append(
                {
                    "hub_id": hub_id,
                    "title": hub.title,
                    "ieee": str(hub.data.get(CONF_IEEE, "")),
                    "area_id": str(hub.data.get(CONF_AREA_ID, "")) or None,
                    "remotes": hub_remotes,
                }
            )
        return self.json({"configured": True, "hubs": hubs_payload})


class EasyIrUiAreasView(http.HomeAssistantView):
    """Return area registry list for hub creation form."""

    url = "/api/easyir/ui/areas"
    name = "api:easyir:ui:areas"
    requires_auth = True

    @callback
    def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[http.KEY_HASS]
        reg = ar.async_get(hass)
        areas = [
            {"area_id": area.id, "name": area.name}
            for area in sorted(reg.areas.values(), key=lambda item: item.name.lower())
        ]
        return self.json({"areas": areas})


class EasyIrUiDiscoverHubsView(http.HomeAssistantView):
    """Return discoverable supported hubs not yet configured."""

    url = "/api/easyir/ui/hubs/discover"
    name = "api:easyir:ui:hubs:discover"
    requires_auth = True

    @callback
    def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[http.KEY_HASS]
        device_reg = dr.async_get(hass)
        choices = list_onboarding_hub_choices(hass)
        devices: list[dict[str, Any]] = []
        for dev_id, label in choices:
            dev = device_reg.async_get(dev_id)
            if dev is None:
                continue
            ieee = ieee_from_zha_device(dev)
            devices.append(
                {
                    "device_id": dev_id,
                    "label": label,
                    "ieee": ieee,
                    "default_name": dev.name_by_user or dev.name or label,
                }
            )
        return self.json({"devices": devices})


class EasyIrUiCreateHubView(http.HomeAssistantView):
    """Create hub subentry from discoverable ZHA TS1201 device."""

    url = "/api/easyir/ui/hubs"
    name = "api:easyir:ui:hubs:create"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[http.KEY_HASS]
        parent = parent_entry(hass)
        if parent is None:
            return self.json_message("EasyIR is not configured", HTTPStatus.BAD_REQUEST)
        try:
            payload = CREATE_HUB_SCHEMA(await request.json())
        except (vol.Invalid, ValueError) as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)

        device_id = str(payload["device_id"]).strip()
        hub_name = str(payload["hub_name"]).strip()
        area_id = str(payload.get(CONF_AREA_ID, "")).strip() or None
        if not hub_name:
            return self.json_message("hub_name is required", HTTPStatus.BAD_REQUEST)

        device_reg = dr.async_get(hass)
        device = device_reg.async_get(device_id)
        if device is None:
            return self.json_message("Device not found", HTTPStatus.BAD_REQUEST)
        ieee = ieee_from_zha_device(device)
        if not ieee:
            return self.json_message("Unable to resolve IEEE", HTTPStatus.BAD_REQUEST)
        if _normalize_ieee(ieee) in configured_hub_ieees(hass):
            return self.json_message("Hub already configured", HTTPStatus.BAD_REQUEST)
        endpoint_id = endpoint_for_zha_device(device)

        unique = _normalize_ieee(ieee)
        existing = {
            str(sub.unique_id)
            for sub in parent.subentries.values()
            if sub.subentry_type == SUBENTRY_TYPE_HUB and sub.unique_id
        }
        if unique in existing:
            return self.json_message("Hub unique id already exists", HTTPStatus.BAD_REQUEST)

        sub_id = f"hub_{uuid4().hex[:10]}"
        subentries = dict(parent.subentries)
        subentries[sub_id] = ConfigSubentry(
            data=MappingProxyType(
                hub_subentry_data(ieee=ieee, endpoint_id=endpoint_id, area_id=area_id)
            ),
            subentry_id=sub_id,
            subentry_type=SUBENTRY_TYPE_HUB,
            title=hub_name,
            unique_id=unique,
        )
        hass.config_entries.async_update_entry(parent, subentries=subentries)
        await _async_reload_parent(hass, parent.entry_id)
        return self.json({"ok": True, "hub_id": sub_id, "ieee": ieee})


class EasyIrUiCatalogView(http.HomeAssistantView):
    """Return wizard catalogs for selected remote type and brand."""

    url = "/api/easyir/ui/catalog"
    name = "api:easyir:ui:catalog"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[http.KEY_HASS]
        remote_type = str(request.query.get("remote_type", "")).strip().lower()
        if remote_type not in {REMOTE_TYPE_CLIMATE, REMOTE_TYPE_TV, REMOTE_TYPE_OTHER}:
            return self.json_message("remote_type is required", HTTPStatus.BAD_REQUEST)
        brand = str(request.query.get("brand", "")).strip()

        options = await async_select_selector_options(hass)
        catalog = catalog_for_remote_type(options, remote_type)
        brands = sorted(catalog.keys(), key=lambda item: item.lower())
        if not brand:
            return self.json(
                {
                    "remote_type": remote_type,
                    "brands": [
                        {"brand": item, "count": len(catalog[item])} for item in brands
                    ],
                }
            )
        if brand not in catalog:
            return self.json_message("Unknown brand", HTTPStatus.BAD_REQUEST)
        return self.json(
            {
                "remote_type": remote_type,
                "brand": brand,
                "devices": catalog[brand],
            }
        )


class EasyIrUiCreateRemoteView(http.HomeAssistantView):
    """Create remote subentry directly from selected wizard profile."""

    url = "/api/easyir/ui/remotes"
    name = "api:easyir:ui:remotes:create"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[http.KEY_HASS]
        parent = parent_entry(hass)
        if parent is None:
            return self.json_message("EasyIR is not configured", HTTPStatus.BAD_REQUEST)
        try:
            payload = CREATE_REMOTE_SCHEMA(await request.json())
        except (vol.Invalid, ValueError) as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)

        hub_id = str(payload["hub_id"]).strip()
        hub = hub_ref_by_id(hass, hub_id)
        if hub is None:
            return self.json_message("Unknown hub_id", HTTPStatus.BAD_REQUEST)

        profile_choice = str(payload["profile_choice"]).strip()
        custom_path = payload.get(CONF_PROFILE_PATH)
        try:
            profile_path = resolve_stored_profile_path(profile_choice, custom_path)
        except ValueError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)

        remote_name = str(payload.get(CONF_REMOTE_NAME, "")).strip() or None
        unique_id, slug = _next_remote_unique_id(
            parent, hub_id=hub_id, profile_path=profile_path
        )
        title = remote_name or f"Remote {slug}"
        if unique_id != f"{hub_id}_{slug}" and not remote_name:
            title = f"Remote {slug} ({unique_id.rsplit('_', 1)[-1]})"

        sub_id = f"remote_{uuid4().hex[:10]}"
        subentries = dict(parent.subentries)
        subentries[sub_id] = ConfigSubentry(
            data=MappingProxyType(
                remote_subentry_data(
                    hub_subentry_id=hub_id,
                    profile_path=profile_path,
                    remote_name=remote_name,
                )
            ),
            subentry_id=sub_id,
            subentry_type=SUBENTRY_TYPE_REMOTE,
            title=title,
            unique_id=unique_id,
        )
        hass.config_entries.async_update_entry(parent, subentries=subentries)
        await _async_reload_parent(hass, parent.entry_id)
        return self.json(
            {
                "ok": True,
                "remote_id": sub_id,
                "title": title,
                "profile_path": profile_path,
                "unique_id": unique_id,
            }
        )


@callback
def async_register_easyir_ui_api(hass: HomeAssistant) -> None:
    """Register EasyIR UI API routes once."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get("_easyir_ui_api_registered"):
        return
    hass.http.register_view(EasyIrUiStateView)
    hass.http.register_view(EasyIrUiAreasView)
    hass.http.register_view(EasyIrUiDiscoverHubsView)
    hass.http.register_view(EasyIrUiCreateHubView)
    hass.http.register_view(EasyIrUiCatalogView)
    hass.http.register_view(EasyIrUiCreateRemoteView)
    root["_easyir_ui_api_registered"] = True

