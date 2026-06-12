"""Button entities representing IR remote keys."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_PROFILE_PATH, CONF_REMOTE_NAME, DOMAIN, ENTRY_KIND_REMOTE
from .hub_registry import entry_kind, hub_entries_for_remote, primary_hub_entry, remote_display_name
from .remote_buttons import RemoteButtonSpec, list_remote_button_specs
from .remote_events import async_fire_button_pressed, async_send_profile_to_hubs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up remote button entities for a remote config entry."""
    if entry_kind(entry) != ENTRY_KIND_REMOTE:
        return
    profile_path = str(entry.data[CONF_PROFILE_PATH])
    specs = await hass.async_add_executor_job(list_remote_button_specs, profile_path)
    entities = [EasyIrRemoteButton(hass, entry, spec) for spec in specs]
    async_add_entities(entities, True)


class EasyIrRemoteButton(ButtonEntity):
    """One remote key that can emit IR via linked hubs or accept state-only updates."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        spec: RemoteButtonSpec,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._spec = spec
        self._pressed = False
        hub = primary_hub_entry(hass, entry)
        hub_ident = (DOMAIN, hub.entry_id) if hub else None
        self._attr_unique_id = f"{entry.entry_id}_btn_{spec.key}"
        self._attr_name = spec.label
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"remote_{entry.entry_id}")},
            name=remote_display_name(entry),
            manufacturer="EasyIR",
            model="Virtual IR Remote",
            via_device=hub_ident,
        )
        self._attr_extra_state_attributes = {
            "button_key": spec.key,
            "remote_entry_id": entry.entry_id,
            "hub_entry_ids": [h.entry_id for h in hub_entries_for_remote(hass, entry)],
            "pressed": False,
        }

    @property
    def spec(self) -> RemoteButtonSpec:
        return self._spec

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        registry = self.hass.data.setdefault(DOMAIN, {}).setdefault("remote_buttons", {})
        registry[(self._entry.entry_id, self._spec.key)] = self

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        registry = self.hass.data.get(DOMAIN, {}).get("remote_buttons", {})
        registry.pop((self._entry.entry_id, self._spec.key), None)

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
            remote_entry_id=self._entry.entry_id,
            button_key=self._spec.key,
            send_ir=send_ir,
            state_change_only=state_change_only,
            entity_id=self.entity_id,
        )
        if send_ir and not state_change_only:
            await async_send_profile_to_hubs(
                self.hass,
                remote_entry=self._entry,
                action=self._spec.action,
                hvac_mode=self._spec.hvac_mode,
                fan_mode=self._spec.fan_mode,
                temperature=self._spec.temperature,
                entity_id=self.entity_id,
            )
