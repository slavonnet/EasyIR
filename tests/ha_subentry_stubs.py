"""Minimal Home Assistant config subentry stubs for unit tests on HA < 2025.7."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

import homeassistant.config_entries as ce


def install() -> None:
    """Patch homeassistant.config_entries when subentries API is missing."""
    if hasattr(ce, "ConfigSubentryFlow"):
        return

    class FlowType(StrEnum):
        CONFIG_FLOW = "config_flow"
        OPTIONS_FLOW = "options_flow"
        CONFIG_SUBENTRIES_FLOW = "config_subentries_flow"

    @dataclass(frozen=True, kw_only=True)
    class ConfigSubentry:
        data: MappingProxyType[str, Any]
        subentry_id: str
        subentry_type: str
        title: str
        unique_id: str | None = None

    class ConfigSubentryFlow(ce.OptionsFlow):
        handler: tuple[str, str]

        @property
        def _entry_id(self) -> str:
            return self.handler[0]

        def _get_entry(self) -> ce.ConfigEntry:
            return self.hass.config_entries.async_get_known_entry(self._entry_id)

        def async_create_entry(self, **kwargs: Any) -> dict[str, Any]:
            result = super().async_create_entry(
                title=kwargs.get("title"),
                data=kwargs.get("data", {}),
            )
            result["unique_id"] = kwargs.get("unique_id")
            return result

    class SubentryFlowContext(dict):
        pass

    class ConfigSubentryFlowManager:
        def __init__(self, hass: Any) -> None:
            self.hass = hass

        async def async_init(self, handler_key: tuple[str, str], *, context=None, data=None):
            entry_id, subentry_type = handler_key
            entry = self.hass.config_entries.async_get_known_entry(entry_id)
            handler = ce.ConfigFlow._handlers[entry.domain]
            subentry_types = handler.async_get_supported_subentry_types(entry)
            flow = subentry_types[subentry_type]()
            flow.hass = self.hass
            flow.handler = handler_key
            flow.context = dict(context or {})
            flow.context["source"] = (context or {}).get("source", ce.SOURCE_USER)
            if data:
                flow.context["discovery_info"] = data
            return await flow.async_step_user()

    _orig_update_entry = ce.ConfigEntries.async_update_entry

    def _patched_update_entry(self, entry, /, **kwargs):
        if "subentries" in kwargs:
            subentries = kwargs.pop("subentries")
            object.__setattr__(entry, "subentries", MappingProxyType(subentries))
        return _orig_update_entry(self, entry, **kwargs)

    def _patched_add_subentry(self, entry, subentry: ConfigSubentry):
        current = dict(getattr(entry, "subentries", {}))
        current[subentry.subentry_id] = subentry
        object.__setattr__(entry, "subentries", MappingProxyType(current))

    ce.FlowType = FlowType
    ce.ConfigSubentry = ConfigSubentry
    ce.ConfigSubentryFlow = ConfigSubentryFlow
    ce.SubentryFlowContext = SubentryFlowContext
    ce.ConfigSubentryFlowManager = ConfigSubentryFlowManager
    ce.ConfigEntries.async_update_entry = _patched_update_entry
    ce.ConfigEntries.async_add_subentry = _patched_add_subentry

    _orig_config_entry_init = ce.ConfigEntry.__init__

    def _patched_config_entry_init(self, *args, **kwargs):
        subentries_data = kwargs.pop("subentries_data", None) or ()
        _orig_config_entry_init(self, *args, **kwargs)
        subentries: dict[str, ConfigSubentry] = {}
        for item in subentries_data:
            sub = ConfigSubentry(
                data=MappingProxyType(dict(item.get("data", {}))),
                subentry_id=item.get("subentry_id", item.get("unique_id", "sub1")),
                subentry_type=item["subentry_type"],
                title=item["title"],
                unique_id=item.get("unique_id"),
            )
            subentries[sub.subentry_id] = sub
        object.__setattr__(self, "subentries", MappingProxyType(subentries))

    ce.ConfigEntry.__init__ = _patched_config_entry_init

    _orig_config_entries_init = ce.ConfigEntries.__init__

    def _patched_config_entries_init(self, hass, _hass_config):
        _orig_config_entries_init(self, hass, _hass_config)
        self.subentries = ConfigSubentryFlowManager(hass)

    ce.ConfigEntries.__init__ = _patched_config_entries_init
