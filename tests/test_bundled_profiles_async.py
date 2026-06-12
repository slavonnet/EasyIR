"""Tests for non-blocking bundled profile option loading."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from custom_components.easyir.bundled_profiles import (
    async_select_selector_options,
    clear_selector_options_cache,
    select_selector_options,
)


class TestBundledProfilesAsync(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_selector_options_cache()

    def tearDown(self) -> None:
        clear_selector_options_cache()

    async def test_async_select_uses_executor(self) -> None:
        hass = MagicMock()
        hass.async_add_executor_job = AsyncMock(
            return_value=[{"value": "demo", "label": "Demo"}]
        )
        options = await async_select_selector_options(hass)
        self.assertEqual(options, [{"value": "demo", "label": "Demo"}])
        hass.async_add_executor_job.assert_awaited_once()

    def test_sync_select_uses_cache_after_async_warmup(self) -> None:
        from custom_components.easyir import bundled_profiles as mod

        mod._SELECTOR_OPTIONS_CACHE = [{"value": "x", "label": "X"}]
        self.assertEqual(select_selector_options(), [{"value": "x", "label": "X"}])


if __name__ == "__main__":
    unittest.main()
