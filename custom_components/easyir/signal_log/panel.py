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
PANEL_JS = "signal_log_panel.js"


async def async_register_signal_log_panel(hass: HomeAssistant) -> None:
    """Serve minimal panel JS and add sidebar entry (idempotent)."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get("_signal_log_panel_registered"):
        return

    static_dir = Path(__file__).resolve().parent.parent / "www"
    if not (static_dir / PANEL_JS).is_file():
        _LOGGER.warning("EasyIR Signal Log panel asset missing: %s", static_dir / PANEL_JS)
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, str(static_dir), cache_headers=True)]
    )

    await panel_custom.async_register_panel(
        hass=hass,
        frontend_url_path="easyir-signal-log",
        webcomponent_name="easyir-signal-log-panel",
        sidebar_title="EasyIR Signal Log",
        sidebar_icon="mdi:remote",
        js_url=f"{URL_BASE}/{PANEL_JS}",
        embed_iframe=True,
        require_admin=False,
        config_panel_domain=DOMAIN,
    )
    root["_signal_log_panel_registered"] = True
