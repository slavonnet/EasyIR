"""Tests for non-blocking profile command encoding path."""

from __future__ import annotations

import asyncio
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

    async def test_send_with_rate_limit_serializes_same_ieee_calls(self) -> None:
        send_lock_by_ieee: dict[str, asyncio.Lock] = {}
        last_send_by_ieee: dict[str, float] = {}
        started = asyncio.Event()
        release = asyncio.Event()
        timeline: list[str] = []
        in_flight = 0
        max_in_flight = 0

        async def _tracked_send(label: str) -> None:
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            timeline.append(f"start:{label}")
            if label == "first":
                started.set()
                await release.wait()
            timeline.append(f"end:{label}")
            in_flight -= 1

        task_first = asyncio.create_task(
            easyir_module._async_send_with_rate_limit(
                ieee="aa:bb",
                send_lock_by_ieee=send_lock_by_ieee,
                last_send_by_ieee=last_send_by_ieee,
                send_delay_s=0.0,
                send_call=partial(_tracked_send, "first"),
            )
        )
        await started.wait()
        task_second = asyncio.create_task(
            easyir_module._async_send_with_rate_limit(
                ieee="aa:bb",
                send_lock_by_ieee=send_lock_by_ieee,
                last_send_by_ieee=last_send_by_ieee,
                send_delay_s=0.0,
                send_call=partial(_tracked_send, "second"),
            )
        )
        await asyncio.sleep(0)
        self.assertFalse(task_second.done())
        release.set()
        await asyncio.gather(task_first, task_second)

        self.assertEqual(max_in_flight, 1)
        self.assertLess(timeline.index("end:first"), timeline.index("start:second"))


if __name__ == "__main__":
    unittest.main()
