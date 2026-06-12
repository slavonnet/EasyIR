"""Mock IR hub transport for dev/testing without physical hardware."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback

from ..const import DOMAIN, EVENT_MOCK_HUB_SENT
from .base import TransportSendContext

_LOGGER = logging.getLogger(__name__)
_MOCK_CALLS_KEY = "mock_hub_calls"


@callback
def get_mock_hub_calls(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return recorded mock hub send calls (newest last)."""
    return list(hass.data.get(DOMAIN, {}).get(_MOCK_CALLS_KEY, []))


class MockIrHubTransport:
    """Log IR payloads instead of sending them to ZHA hardware."""

    async def send(self, hass: HomeAssistant, code: str, ctx: TransportSendContext) -> None:
        """Record payload and emit a bus event for automations/tests."""
        record = {
            "ieee": ctx.ieee,
            "endpoint_id": ctx.endpoint_id,
            "code": code,
        }
        root = hass.data.setdefault(DOMAIN, {})
        calls: list[dict[str, Any]] = root.setdefault(_MOCK_CALLS_KEY, [])
        calls.append(record)
        _LOGGER.warning(
            "Mock IR hub send ieee=%s endpoint=%s code_len=%s code=%s",
            ctx.ieee,
            ctx.endpoint_id,
            len(code),
            code[:80] + ("..." if len(code) > 80 else ""),
        )
        hass.bus.async_fire(EVENT_MOCK_HUB_SENT, record)

    def describe(self) -> dict[str, Any]:
        return {"transport": "mock", "description": "EasyIR mock IR hub (logs only)"}
