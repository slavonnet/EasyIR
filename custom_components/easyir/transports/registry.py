"""Resolve IR transport adapters by hub transport id."""

from __future__ import annotations

from typing import Any, Mapping

from homeassistant.core import HomeAssistant

from ..const import CONF_TRANSPORT, DOMAIN, TRANSPORT_MOCK, TRANSPORT_TS1201_ZHA
from .base import IrTransport
from .mock import MockIrHubTransport
from .ts1201_zha import Ts1201ZhaTransport


def transport_for_hub(hass: HomeAssistant, hub_data: Mapping[str, Any]) -> IrTransport:
    """Return transport adapter for hub subentry/entry data."""
    transport_id = str(hub_data.get(CONF_TRANSPORT, TRANSPORT_TS1201_ZHA)).strip()
    registry: dict[str, IrTransport] = hass.data.setdefault(DOMAIN, {}).setdefault(
        "transports", {}
    )
    if transport_id == TRANSPORT_MOCK:
        return registry.setdefault(TRANSPORT_MOCK, MockIrHubTransport())
    return registry.setdefault(TRANSPORT_TS1201_ZHA, Ts1201ZhaTransport())
