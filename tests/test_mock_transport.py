"""Tests for mock IR hub transport."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from custom_components.easyir.const import DOMAIN, EVENT_MOCK_HUB_SENT, TRANSPORT_MOCK
from custom_components.easyir.transports import get_mock_hub_calls, transport_for_hub
from custom_components.easyir.transports.base import TransportSendContext
from custom_components.easyir.transports.mock import MockIrHubTransport


class TestMockTransport(unittest.IsolatedAsyncioTestCase):
    async def test_send_records_call_and_fires_event(self) -> None:
        hass = MagicMock()
        hass.data = {DOMAIN: {}}
        hass.bus = MagicMock()
        transport = MockIrHubTransport()
        ctx = TransportSendContext(ieee="aa:bb:cc:dd:ee:ff:00:01", endpoint_id=1)

        await transport.send(hass, "BASE64CODE", ctx)

        calls = get_mock_hub_calls(hass)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["code"], "BASE64CODE")
        self.assertEqual(calls[0]["ieee"], ctx.ieee)
        hass.bus.async_fire.assert_called_once_with(
            EVENT_MOCK_HUB_SENT,
            {"ieee": ctx.ieee, "endpoint_id": 1, "code": "BASE64CODE"},
        )

    def test_transport_for_hub_selects_mock(self) -> None:
        hass = MagicMock()
        hass.data = {DOMAIN: {}}
        transport = transport_for_hub(hass, {"transport": TRANSPORT_MOCK, "ieee": "x"})
        self.assertIsInstance(transport, MockIrHubTransport)
