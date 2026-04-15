"""Climate entity for EasyIR."""

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

from .const import CONF_ENDPOINT_ID, CONF_IEEE, CONF_PROFILE_PATH, DOMAIN, SERVICE_SEND_COMMAND


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EasyIR climate entity from config entry."""
    async_add_entities([EasyIrClimate(hass, entry)], True)


class EasyIrClimate(ClimateEntity):
    """Optimistic climate entity backed by EasyIR service calls."""

    _attr_has_entity_name = True
    _attr_name = "AC"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.DRY]
    _attr_fan_modes = ["auto", "low", "mid", "high"]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    _attr_min_temp = 18
    _attr_max_temp = 30
    _attr_target_temperature_step = 1

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize entity."""
        self.hass = hass
        self._entry = entry
        self._ieee = str(entry.data[CONF_IEEE])
        self._profile_path = str(entry.data[CONF_PROFILE_PATH])
        self._endpoint_id = int(entry.data[CONF_ENDPOINT_ID])
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ieee)},
            manufacturer="EasyIR",
            model="Tuya TS1201 (ZHA)",
            name="EasyIR Bridge",
        )
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_fan_mode = "auto"
        self._attr_target_temperature = 24

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
        self.async_write_ha_state()

    async def _send(self, data: dict[str, Any]) -> None:
        """Send command via integration service."""
        payload = {
            CONF_IEEE: self._ieee,
            CONF_PROFILE_PATH: self._profile_path,
            CONF_ENDPOINT_ID: self._endpoint_id,
            **data,
        }
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_COMMAND,
            payload,
            blocking=True,
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
