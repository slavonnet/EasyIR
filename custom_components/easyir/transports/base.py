"""Abstract transport adapter for sending IR payloads to physical hubs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from homeassistant.core import HomeAssistant


@dataclass(frozen=True, slots=True)
class TransportSendContext:
    """Per-send addressing context (transport-specific fields live here)."""

    ieee: str
    endpoint_id: int


@runtime_checkable
class IrTransport(Protocol):
    """Deliver encoded hub payloads (for example TS1201 base64) to the integration."""

    async def send(self, hass: HomeAssistant, code: str, ctx: TransportSendContext) -> None:
        """Send payload to the hub identified by ctx."""

    def describe(self) -> dict[str, Any]:
        """Opaque metadata for logging or diagnostics (must be JSON-serializable)."""
