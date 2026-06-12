"""Climate entity for EasyIR remote (virtual AC)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_PROFILE_PATH, DOMAIN, ENTRY_KIND_REMOTE
from .hub_registry import (
    entry_kind,
    hub_entries_for_remote,
    hub_transport_data,
    primary_hub_entry,
    remote_display_name,
)
from .protocols.lg_p12rk import climate_capability_view
from .remote_events import async_send_profile_to_hubs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EasyIR climate entity from a remote config entry."""
    if entry_kind(entry) != ENTRY_KIND_REMOTE:
        return
    profile_path = str(entry.data[CONF_PROFILE_PATH])
    cap_view = await hass.async_add_executor_job(climate_capability_view, profile_path)
    async_add_entities([EasyIrClimate(hass, entry, cap_view=cap_view)], True)


class EasyIrClimate(ClimateEntity):
    """Optimistic climate entity backed by EasyIR remote + hub transport."""

    _attr_has_entity_name = True
    _attr_name = "AC"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.DRY]
    _attr_fan_modes = ["auto", "low", "mid", "high"]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    _attr_min_temp = 18
    _attr_max_temp = 30
    _attr_target_temperature_step = 1

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, *, cap_view: dict[str, Any] | None = None
    ) -> None:
        """Initialize entity."""
        self.hass = hass
        self._entry = entry
        self._profile_path = str(entry.data[CONF_PROFILE_PATH])
        self._cap_view = cap_view or {"protocol": "legacy_profile", "pilot": False}
        self._attr_extra_state_attributes = {}
        self._apply_capability_view(self._cap_view)
        self._attr_unique_id = f"{entry.entry_id}_climate"
        hub = primary_hub_entry(hass, entry)
        hub_ident = (DOMAIN, hub.entry_id) if hub else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"remote_{entry.entry_id}")},
            manufacturer="EasyIR",
            model="Virtual IR Remote",
            name=remote_display_name(entry),
            via_device=hub_ident,
        )
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_fan_mode = "auto"
        self._attr_target_temperature = 24
        self._attr_extra_state_attributes = {
            "hub_entry_ids": [h.entry_id for h in hub_entries_for_remote(hass, entry)],
        }

    def _apply_capability_view(self, view: dict) -> None:
        """Set entity mode/temperature constraints from capability map when pilot."""
        if not view.get("pilot"):
            self._attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.DRY]
            self._attr_fan_modes = ["auto", "low", "mid", "high"]
            self._attr_min_temp = 18
            self._attr_max_temp = 30
            self._attr_target_temperature_step = 1
            return

        mode_map = {
            "off": HVACMode.OFF,
            "cool": HVACMode.COOL,
            "dry": HVACMode.DRY,
            "heat": HVACMode.HEAT,
            "fan_only": HVACMode.FAN_ONLY,
            "auto": HVACMode.AUTO,
        }
        hvac_ids = [str(x) for x in view.get("hvac_modes", [])]
        modes: list[HVACMode] = []
        for mid in hvac_ids:
            ha_mode = mode_map.get(mid)
            if ha_mode is not None and ha_mode not in modes:
                modes.append(ha_mode)
        self._attr_hvac_modes = modes

        self._attr_fan_modes = [str(x) for x in view.get("fan_modes", [])]
        tc = view.get("temperature_c") or {}
        self._attr_min_temp = float(tc.get("min", 18))
        self._attr_max_temp = float(tc.get("max", 30))
        self._attr_target_temperature_step = float(tc.get("step", 1))
        self._attr_extra_state_attributes = {
            "easyir_protocol": view.get("protocol"),
            "easyir_pilot": True,
            "easyir_ionizer_supported": bool(view.get("ionizer_supported")),
            "easyir_energy_saving_supported": bool(view.get("energy_saving_supported")),
            "easyir_auto_clean_supported": bool(view.get("auto_clean_supported")),
            "hub_entry_ids": [h.entry_id for h in hub_entries_for_remote(self.hass, self._entry)],
        }

    async def async_added_to_hass(self) -> None:
        """Register for inbound decoded IR sync."""
        await super().async_added_to_hass()
        self.hass.data.setdefault(DOMAIN, {}).setdefault("climate_entities", {})[
            self.entity_id
        ] = self

    async def async_will_remove_from_hass(self) -> None:
        """Unregister entity reference for inbound sync."""
        await super().async_will_remove_from_hass()
        entities = self.hass.data.get(DOMAIN, {}).get("climate_entities", {})
        entities.pop(self.entity_id, None)

    @callback
    def async_handle_easyir_inbound_decoded(self, decoded: dict[str, Any]) -> None:
        """Apply decoded inbound IR state when room policy allows (no ZHA send)."""
        if (hvac := decoded.get("hvac_mode")) is not None:
            try:
                self._attr_hvac_mode = HVACMode(str(hvac))
            except ValueError:
                pass
        if (fan := decoded.get("fan_mode")) is not None:
            self._attr_fan_mode = str(fan)
        if (temp := decoded.get("temperature")) is not None:
            try:
                self._attr_target_temperature = float(temp)
            except (TypeError, ValueError):
                pass
        ff = decoded.get("feature_flags")
        if isinstance(ff, dict) and self._cap_view.get("pilot"):
            attrs = dict(self._attr_extra_state_attributes or {})
            if self._cap_view.get("ionizer_supported") and "ionizer" in ff:
                attrs["easyir_ionizer_on"] = bool(ff["ionizer"])
            if self._cap_view.get("energy_saving_supported") and "energy_saving" in ff:
                attrs["easyir_energy_saving_on"] = bool(ff["energy_saving"])
            if self._cap_view.get("auto_clean_supported") and "auto_clean" in ff:
                attrs["easyir_auto_clean_on"] = bool(ff["auto_clean"])
            self._attr_extra_state_attributes = attrs
        self.async_write_ha_state()

    async def _send(self, data: dict[str, Any]) -> None:
        """Send command via remote profile to all linked hubs."""
        await async_send_profile_to_hubs(
            self.hass,
            remote_entry=self._entry,
            action=str(data["action"]),
            hvac_mode=data.get("hvac_mode"),
            fan_mode=data.get("fan_mode"),
            temperature=data.get("temperature"),
            entity_id=self.entity_id,
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self._send({"action": "off"})
            self._attr_hvac_mode = HVACMode.OFF
        elif hvac_mode in (HVACMode.COOL, HVACMode.DRY):
            mode = hvac_mode.value
            await self._send(
                {
                    "action": mode,
                    "hvac_mode": mode,
                    "fan_mode": self._attr_fan_mode,
                    "temperature": int(self._attr_target_temperature),
                }
            )
            self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature and send command when active."""
        if (temperature := kwargs.get("temperature")) is None:
            return
        self._attr_target_temperature = float(temperature)
        if self._attr_hvac_mode in (HVACMode.COOL, HVACMode.DRY):
            mode = self._attr_hvac_mode.value
            await self._send(
                {
                    "action": mode,
                    "hvac_mode": mode,
                    "fan_mode": self._attr_fan_mode,
                    "temperature": int(self._attr_target_temperature),
                }
            )
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode and send command when active."""
        self._attr_fan_mode = fan_mode
        if self._attr_hvac_mode in (HVACMode.COOL, HVACMode.DRY):
            mode = self._attr_hvac_mode.value
            await self._send(
                {
                    "action": mode,
                    "hvac_mode": mode,
                    "fan_mode": fan_mode,
                    "temperature": int(self._attr_target_temperature),
                }
            )
        self.async_write_ha_state()
