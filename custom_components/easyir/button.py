"""Button entities representing IR remote keys."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_PROFILE_PATH, DOMAIN
from .devices import hub_device_identifier, remote_device_identifier
from .hub_registry import (
    RemoteRef,
    hub_refs_for_remote,
    iter_remote_refs,
    primary_hub_ref,
    remote_display_name,
)
from .remote_buttons import ButtonCommandKind, RemoteButtonSpec, list_remote_button_specs
from .remote_events import async_fire_button_pressed, async_send_profile_to_hubs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up remote button entities for remote subentries."""
    entities: list[EasyIrRemoteButton] = []
    for remote in iter_remote_refs(hass, entry):
        profile_path = str(remote.data[CONF_PROFILE_PATH])
        specs = await hass.async_add_executor_job(list_remote_button_specs, profile_path)
        entities.extend(EasyIrRemoteButton(hass, remote, spec) for spec in specs)
    if entities:
        async_add_entities(entities, True)


class EasyIrRemoteButton(ButtonEntity):
    """One remote key that can emit IR via linked hubs or accept state-only updates."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        remote: RemoteRef,
        spec: RemoteButtonSpec,
    ) -> None:
        self.hass = hass
        self._remote = remote
        self._spec = spec
        self._pressed = False
        hub = primary_hub_ref(hass, remote)
        hub_ident = hub_device_identifier(hub.subentry_id) if hub else None
        self._attr_unique_id = f"{remote.subentry_id}_btn_{spec.key}"
        self._attr_name = spec.label
        self._attr_device_info = DeviceInfo(
            identifiers={remote_device_identifier(remote.subentry_id)},
            name=remote_display_name(remote),
            manufacturer="EasyIR",
            model="Virtual IR Remote",
            via_device=hub_ident,
        )
        self._attr_extra_state_attributes = {
            "button_key": spec.key,
            "command_kind": spec.kind.value,
            "remote_entry_id": remote.subentry_id,
            "hub_entry_ids": [h.subentry_id for h in hub_refs_for_remote(hass, remote)],
            "pressed": False,
        }
        if spec.feature_key:
            self._attr_extra_state_attributes["feature_key"] = spec.feature_key

    @property
    def spec(self) -> RemoteButtonSpec:
        return self._spec

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        registry = self.hass.data.setdefault(DOMAIN, {}).setdefault("remote_buttons", {})
        registry[(self._remote.subentry_id, self._spec.key)] = self

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        registry = self.hass.data.get(DOMAIN, {}).get("remote_buttons", {})
        registry.pop((self._remote.subentry_id, self._spec.key), None)

    def _write_pressed_state(self, pressed: bool) -> None:
        self._pressed = pressed
        attrs = dict(self._attr_extra_state_attributes or {})
        attrs["pressed"] = pressed
        self._attr_extra_state_attributes = attrs
        self.async_write_ha_state()

    async def async_press(self) -> None:
        """User pressed the button: update state, fire event, send IR."""
        await self.async_handle_external_command(send_ir=True, state_change_only=False)

    async def async_handle_external_command(
        self, *, send_ir: bool, state_change_only: bool
    ) -> None:
        """Handle UI press or automation/inbound-sync command."""
        self._write_pressed_state(True)
        async_fire_button_pressed(
            self.hass,
            remote_entry_id=self._remote.subentry_id,
            button_key=self._spec.key,
            send_ir=send_ir,
            state_change_only=state_change_only,
            entity_id=self.entity_id,
        )
        if send_ir and not state_change_only:
            hvac_mode = self._spec.hvac_mode
            fan_mode = self._spec.fan_mode
            temperature = self._spec.temperature
            if self._spec.kind == ButtonCommandKind.FEATURE_COMMAND:
                hvac_mode = None
                fan_mode = None
                temperature = None
            await async_send_profile_to_hubs(
                self.hass,
                remote=self._remote,
                action=self._spec.action,
                hvac_mode=hvac_mode,
                fan_mode=fan_mode,
                temperature=temperature,
                entity_id=self.entity_id,
            )
            if self._spec.feature_key and self._spec.action.endswith("_on"):
                attrs = dict(self._attr_extra_state_attributes or {})
                attrs[f"feature_{self._spec.feature_key}_on"] = True
                self._attr_extra_state_attributes = attrs
            elif self._spec.feature_key and self._spec.action.endswith("_off"):
                attrs = dict(self._attr_extra_state_attributes or {})
                attrs[f"feature_{self._spec.feature_key}_on"] = False
                self._attr_extra_state_attributes = attrs
