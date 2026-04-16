"""Tests for per-IEEE pooled dispatcher with deduplication and pacing."""

from __future__ import annotations

import asyncio
import unittest

from custom_components.easyir.command_pool import ServiceCallPool


class _FakeServices:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._release_next = asyncio.Event()

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict,
        *,
        blocking: bool = True,
        return_response: bool = False,
    ):
        self.calls.append(
            {
                "domain": domain,
                "service": service,
                "data": dict(data),
                "blocking": blocking,
                "return_response": return_response,
            }
        )
        await self._release_next.wait()
        return {"ok": True, "echo": dict(data)}


class _FakeHass:
    def __init__(self) -> None:
        self.services = _FakeServices()


class TestCommandPool(unittest.IsolatedAsyncioTestCase):
    async def test_deduplicates_same_pending_payload(self) -> None:
        hass = _FakeHass()
        pool = ServiceCallPool(hass, min_interval_s=0.0)
        payload = {"ieee": "aa:bb", "cluster_id": 0xE004, "params": {"code": "abc"}}

        task1 = asyncio.create_task(
            pool.async_call(
                ieee="aa:bb",
                domain="zha",
                service="issue_zigbee_cluster_command",
                data=payload,
                return_response=True,
            )
        )
        task2 = asyncio.create_task(
            pool.async_call(
                ieee="aa:bb",
                domain="zha",
                service="issue_zigbee_cluster_command",
                data=payload,
                return_response=True,
            )
        )

        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertEqual(len(hass.services.calls), 1)
        hass.services._release_next.set()
        res1, res2 = await asyncio.gather(task1, task2)
        self.assertEqual(res1, res2)
        self.assertEqual(len(hass.services.calls), 1)

    async def test_serializes_calls_same_ieee(self) -> None:
        hass = _FakeHass()
        pool = ServiceCallPool(hass, min_interval_s=0.0)

        task1 = asyncio.create_task(
            pool.async_call(
                ieee="aa:bb",
                domain="zha",
                service="issue_zigbee_cluster_command",
                data={"params": {"code": "first"}},
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertEqual(len(hass.services.calls), 1)

        task2 = asyncio.create_task(
            pool.async_call(
                ieee="aa:bb",
                domain="zha",
                service="issue_zigbee_cluster_command",
                data={"params": {"code": "second"}},
            )
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        # second call is queued until first completes
        self.assertEqual(len(hass.services.calls), 1)
        hass.services._release_next.set()
        await task1
        await asyncio.sleep(0)
        self.assertEqual(len(hass.services.calls), 2)
        await task2

    async def test_applies_min_interval_between_calls(self) -> None:
        hass = _FakeHass()
        marks: list[float] = []

        now = 0.0

        async def _sleep(delay: float) -> None:
            nonlocal now
            now += delay

        def _monotonic() -> float:
            return now

        class _TimedServices(_FakeServices):
            async def async_call(self, *args, **kwargs):  # type: ignore[override]
                marks.append(now)
                return await super().async_call(*args, **kwargs)

        hass.services = _TimedServices()
        hass.services._release_next.set()
        pool = ServiceCallPool(
            hass,
            min_interval_s=1.0,
            monotonic=_monotonic,
            sleeper=_sleep,
        )
        await pool.async_call(
            ieee="aa:bb",
            domain="zha",
            service="issue_zigbee_cluster_command",
            data={"params": {"code": "first"}},
        )
        await pool.async_call(
            ieee="aa:bb",
            domain="zha",
            service="issue_zigbee_cluster_command",
            data={"params": {"code": "second"}},
        )
        self.assertEqual(len(marks), 2)
        self.assertGreaterEqual(marks[1] - marks[0], 1.0)

    async def test_priority_executes_lower_number_first(self) -> None:
        hass = _FakeHass()
        pool = ServiceCallPool(hass, min_interval_s=0.0)
        hass.services._release_next.set()

        low = asyncio.create_task(
            pool.async_call(
                ieee="aa:bb",
                domain="zha",
                service="issue_zigbee_cluster_command",
                data={"params": {"code": "low"}},
                priority=10,
            )
        )
        high = asyncio.create_task(
            pool.async_call(
                ieee="aa:bb",
                domain="zha",
                service="issue_zigbee_cluster_command",
                data={"params": {"code": "high"}},
                priority=0,
            )
        )
        await asyncio.gather(low, high)
        self.assertEqual(len(hass.services.calls), 2)
        self.assertEqual(hass.services.calls[0]["data"]["params"]["code"], "high")
        self.assertEqual(hass.services.calls[1]["data"]["params"]["code"], "low")

    async def test_dedupe_can_be_disabled(self) -> None:
        hass = _FakeHass()
        pool = ServiceCallPool(hass, min_interval_s=0.0)
        payload = {"params": {"code": "same"}}
        hass.services._release_next.set()
        await asyncio.gather(
            pool.async_call(
                ieee="aa:bb",
                domain="zha",
                service="issue_zigbee_cluster_command",
                data=payload,
                dedupe=False,
            ),
            pool.async_call(
                ieee="aa:bb",
                domain="zha",
                service="issue_zigbee_cluster_command",
                data=payload,
                dedupe=False,
            ),
        )
        self.assertEqual(len(hass.services.calls), 2)


if __name__ == "__main__":
    unittest.main()
