"""ZHA cluster transport for Tuya TS1201 IR blasters."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from ..const import (
    TS1201_CLUSTER_ID,
    TS1201_CLUSTER_TYPE,
    TS1201_COMMAND_ID,
    TS1201_COMMAND_TYPE,
    ZHA_DOMAIN,
    ZHA_SERVICE,
)
from .base import TransportSendContext


class Ts1201ZhaTransport:
    """Send TS1201 base64 payloads via ZHA issue_zigbee_cluster_command."""

    async def send(self, hass: HomeAssistant, code: str, ctx: TransportSendContext) -> None:
        """Issue ZHA cluster command 2 on 0xE004 with params code."""
        payload: dict[str, Any] = {
            "ieee": ctx.ieee,
            "endpoint_id": ctx.endpoint_id,
            "cluster_id": TS1201_CLUSTER_ID,
            "cluster_type": TS1201_CLUSTER_TYPE,
            "command": TS1201_COMMAND_ID,
            "command_type": TS1201_COMMAND_TYPE,
            "params": {"code": code},
        }
        await hass.services.async_call(
            ZHA_DOMAIN,
            ZHA_SERVICE,
            payload,
            blocking=True,
        )

    def describe(self) -> dict[str, Any]:
        """Return static cluster metadata for diagnostics."""
        return {
            "transport": "ts1201_zha",
            "zha_service": ZHA_SERVICE,
            "cluster_id": hex(TS1201_CLUSTER_ID),
            "command_id": TS1201_COMMAND_ID,
        }
