"""Tests for non-blocking profile command encoding path."""

from __future__ import annotations

from functools import partial
import unittest
from unittest.mock import AsyncMock, patch

from custom_components import easyir as easyir_module


class _FakeHass:
    def __init__(self) -> None:
        self.async_add_executor_job = AsyncMock(return_value=("frame", "code"))


class TestAsyncSendCommandExecutor(unittest.IsolatedAsyncioTestCase):
    async def test_profile_encoding_is_scheduled_in_executor(self) -> None:
        hass = _FakeHass()
        with patch(
            "custom_components.easyir.encode_profile_command_for_zha_ts1201",
            return_value=("frame", "code"),
        ):
            result = await easyir_module._async_encode_profile_command_for_transport(
                hass,
                profile_path="/tmp/profile.json",
                action="off",
                hvac_mode=None,
                fan_mode=None,
                temperature=None,
            )

        self.assertEqual(result, ("frame", "code"))
        hass.async_add_executor_job.assert_awaited_once()

        scheduled = hass.async_add_executor_job.await_args.args[0]
        self.assertIsInstance(scheduled, partial)
        self.assertEqual(scheduled.keywords["profile_path"], "/tmp/profile.json")
        self.assertEqual(scheduled.keywords["action"], "off")
        self.assertIsNone(scheduled.keywords["hvac_mode"])
        self.assertIsNone(scheduled.keywords["fan_mode"])
        self.assertIsNone(scheduled.keywords["temperature"])


if __name__ == "__main__":
    unittest.main()
