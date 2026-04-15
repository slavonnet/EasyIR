"""Tests for Signal Log sidebar panel registration."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from custom_components.easyir.const import DOMAIN
from custom_components.easyir.signal_log.panel import async_register_signal_log_panel


class _FakeHttp:
    def __init__(self) -> None:
        self.async_register_static_paths = AsyncMock()


class _FakeHass:
    def __init__(self) -> None:
        self.data: dict = {}
        self.http = _FakeHttp()


class TestSignalLogPanel(unittest.IsolatedAsyncioTestCase):
    async def test_register_panel_uses_webcomponent_not_iframe(self) -> None:
        hass = _FakeHass()
        with patch(
            "custom_components.easyir.signal_log.panel.panel_custom.async_register_panel",
            new=AsyncMock(),
        ) as register_panel:
            await async_register_signal_log_panel(SimpleNamespace(**hass.__dict__))

        register_panel.assert_awaited_once()
        kwargs = register_panel.await_args.kwargs
        self.assertEqual(kwargs["webcomponent_name"], "easyir-signal-log-panel")
        self.assertFalse(kwargs["embed_iframe"])
        self.assertEqual(kwargs["frontend_url_path"], "easyir-signal-log")

    async def test_register_is_idempotent(self) -> None:
        hass = _FakeHass()
        with patch(
            "custom_components.easyir.signal_log.panel.panel_custom.async_register_panel",
            new=AsyncMock(),
        ) as register_panel:
            ns = SimpleNamespace(**hass.__dict__)
            await async_register_signal_log_panel(ns)
            await async_register_signal_log_panel(ns)

        register_panel.assert_awaited_once()
        self.assertTrue(ns.data[DOMAIN]["_signal_log_panel_registered"])


if __name__ == "__main__":
    unittest.main()
