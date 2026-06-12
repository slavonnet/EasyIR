"""Register EasyIR sidebar panel (Signal Log) when frontend is available."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/easyir_static"
SIGNAL_LOG_PANEL_JS = "signal_log_panel_v2.js"
MAIN_PANEL_JS = "easyir_panel_v1.js"


async def async_register_signal_log_panel(hass: HomeAssistant) -> None:
    """Serve EasyIR panel assets and register sidebar entries (idempotent)."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get("_signal_log_panel_registered"):
        return

    static_dir = Path(__file__).resolve().parent.parent / "www"
    if not (static_dir / SIGNAL_LOG_PANEL_JS).is_file():
        _LOGGER.warning(
            "EasyIR Signal Log panel asset missing: %s", static_dir / SIGNAL_LOG_PANEL_JS
        )
        return
    if not (static_dir / MAIN_PANEL_JS).is_file():
        _LOGGER.warning("EasyIR main panel asset missing: %s", static_dir / MAIN_PANEL_JS)
        return

    await hass.http.async_register_static_paths(
        # Keep cache headers disabled to avoid stale panel JS after upgrades.
        [StaticPathConfig(URL_BASE, str(static_dir), cache_headers=False)]
    )

    await panel_custom.async_register_panel(
        hass=hass,
        frontend_url_path="easyir",
        webcomponent_name="easyir-main-panel",
        sidebar_title="EasyIR",
        sidebar_icon="mdi:remote-tv",
        js_url=f"{URL_BASE}/{MAIN_PANEL_JS}",
        embed_iframe=False,
        require_admin=False,
        config_panel_domain=DOMAIN,
    )

    await panel_custom.async_register_panel(
        hass=hass,
        frontend_url_path="easyir-signal-log",
        webcomponent_name="easyir-signal-log-panel",
        sidebar_title="EasyIR Signal Log",
        sidebar_icon="mdi:remote",
        js_url=f"{URL_BASE}/{SIGNAL_LOG_PANEL_JS}",
        embed_iframe=False,
        require_admin=False,
        config_panel_domain=DOMAIN,
    )
    root["_signal_log_panel_registered"] = True
