"""Tests for EasyIR one-shot IR learn flow."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from custom_components.easyir import learn as learn_module
from custom_components.easyir.const import (
    TS1201_CLUSTER_ID,
    TS1201_IRLEARN_COMMAND_ID,
    ZHA_DOMAIN,
    ZHA_SERVICE,
)


class _FakeServices:
    def __init__(self, calls: list, responses: list | None = None) -> None:
        self._calls = calls
        self._responses = list(responses or [])

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict,
        blocking: bool = True,
        return_response: bool = False,
    ):
        self._calls.append(
            {
                "domain": domain,
                "service": service,
                "data": dict(data),
                "blocking": blocking,
                "return_response": return_response,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return {}


class _FakeHass:
    def __init__(self, responses: list | None = None) -> None:
        self._calls: list[dict] = []
        self.services = _FakeServices(self._calls, responses=responses)
        self.data = {}
        default_entry = type(
            "Entry",
            (),
            {"entry_id": "hub-default", "data": {"ieee": "aa:bb:cc", "endpoint_id": 1}},
        )()
        self.config_entries = type(
            "Cfg",
            (),
            {
                "async_entries": (
                    lambda _self, _domain: [
                        default_entry
                    ]
                )
            },
        )()

    @property
    def calls(self) -> list[dict]:
        return self._calls


class TestLearnFlow(unittest.IsolatedAsyncioTestCase):
    async def test_learn_once_ts1201_returns_code_and_disables_learning(self) -> None:
        hass = _FakeHass(
            responses=[
                {},  # enable learn
                {"success": {0: "QWxhZGRpbjpvcGVuIHNlc2FtZQ=="}},  # read attribute
                {},  # disable learn
            ]
        )
        code = await learn_module.learn_once_ts1201(
            hass,
            ieee="aa:bb:cc",
            endpoint_id=1,
            timeout_s=1.0,
            poll_interval_s=0.01,
        )
        self.assertEqual(code, "QWxhZGRpbjpvcGVuIHNlc2FtZQ==")
        self.assertEqual(len(hass.calls), 2)
        start_call = hass.calls[0]
        self.assertEqual(start_call["domain"], ZHA_DOMAIN)
        self.assertEqual(start_call["service"], ZHA_SERVICE)
        self.assertEqual(start_call["data"]["cluster_id"], TS1201_CLUSTER_ID)
        self.assertEqual(start_call["data"]["command"], TS1201_IRLEARN_COMMAND_ID)
        self.assertEqual(start_call["data"]["params"], {"on_off": True})
        self.assertEqual(len(hass.calls), 2)

    async def test_learn_once_disables_mode_on_timeout(self) -> None:
        hass = _FakeHass(responses=[{}, {"success": {}}, {"success": {}}, {}])
        with self.assertRaises(TimeoutError):
            await learn_module.learn_once_ts1201(
                hass,
                ieee="aa:bb:cc",
                endpoint_id=1,
                timeout_s=0.02,
                poll_interval_s=0.01,
            )
        self.assertGreaterEqual(len(hass.calls), 2)
        self.assertEqual(hass.calls[0]["data"]["params"], {"on_off": True})

    async def test_learn_once_dispatch_uses_ts1201_profile(self) -> None:
        hass = _FakeHass(
            responses=[
                {},
                {"success": {0: "ABC"}},
                {},
            ]
        )
        payload = await learn_module.learn_once(
            hass,
            ieee="aa:bb:cc",
            timeout_s=5,
            poll_interval_s=0.01,
        )
        self.assertEqual(payload["code"], "ABC")
        self.assertEqual(payload["vendor_profile"], learn_module.VENDOR_PROFILE_TS1201_ZOSUNG)
        self.assertEqual(payload["endpoint_id"], 1)
        self.assertEqual(payload["hub_id"], None)

    async def test_learn_once_resolves_target_by_hub_id(self) -> None:
        hass = _FakeHass(
            responses=[
                {},
                {"success": {0: "CODE_BY_HUB"}},
            ]
        )
        hub_entry = type(
            "Entry",
            (),
            {"entry_id": "hub-1", "data": {"ieee": "11:22:33", "endpoint_id": 5}},
        )()
        hass.config_entries = type(
            "Cfg",
            (),
            {"async_entries": lambda _self, _domain: [hub_entry]},
        )()

        payload = await learn_module.learn_once(
            hass,
            hub_id="hub-1",
            timeout_s=5,
            poll_interval_s=0.01,
        )
        self.assertEqual(payload["code"], "CODE_BY_HUB")
        self.assertEqual(payload["ieee"], "11:22:33")
        self.assertEqual(payload["endpoint_id"], 5)
        self.assertEqual(payload["hub_id"], "hub-1")
        self.assertEqual(hass.calls[0]["data"]["ieee"], "11:22:33")
        self.assertEqual(hass.calls[0]["data"]["endpoint_id"], 5)

    async def test_resolve_learn_target_rejects_conflicting_hub_and_ieee(self) -> None:
        hass = _FakeHass()
        hub_entry = type(
            "Entry",
            (),
            {"entry_id": "hub-1", "data": {"ieee": "11:22:33", "endpoint_id": 5}},
        )()
        hass.config_entries = type(
            "Cfg",
            (),
            {"async_entries": lambda _self, _domain: [hub_entry]},
        )()
        with self.assertRaises(ValueError):
            await learn_module.async_resolve_learn_target(
                hass,
                hub_id="hub-1",
                ieee="aa:bb:cc",
                endpoint_id=None,
            )

    async def test_async_start_ir_learning_respects_explicit_endpoint(self) -> None:
        hass = _FakeHass(responses=[{}])
        result = await learn_module.async_start_ir_learning(
            hass,
            ieee="aa:bb:cc",
            vendor_profile=learn_module.VENDOR_PROFILE_TS1201_ZOSUNG,
            timeout_s=7,
            endpoint_id=2,
        )
        self.assertEqual(result["status"], "learning")
        self.assertEqual(hass.calls[0]["data"]["endpoint_id"], 2)

    async def test_read_last_learned_falls_back_when_read_service_missing(self) -> None:
        class _ServiceNotFound(Exception):
            pass

        class _FallbackServices(_FakeServices):
            async def async_call(  # type: ignore[override]
                self,
                domain: str,
                service: str,
                data: dict,
                blocking: bool = True,
                return_response: bool = False,
            ):
                self._calls.append(
                    {
                        "domain": domain,
                        "service": service,
                        "data": dict(data),
                        "blocking": blocking,
                        "return_response": return_response,
                    }
                )
                if service == "read_zigbee_cluster_attributes":
                    raise _ServiceNotFound("Action not found")
                return {"success": {0: "ABC123"}}

        hass = _FakeHass(responses=[])
        hass.services = _FallbackServices(hass.calls, responses=[])

        payload = await learn_module.learn_once(
            hass,
            ieee="aa:bb:cc",
            endpoint_id=1,
            timeout_s=1,
            poll_interval_s=0.01,
        )

        self.assertEqual(payload["code"], "ABC123")
        self.assertGreaterEqual(len(hass.calls), 2)
        self.assertEqual(hass.calls[0]["service"], ZHA_SERVICE)
        self.assertEqual(hass.calls[1]["service"], "read_zigbee_cluster_attributes")
        self.assertEqual(hass.calls[2]["service"], ZHA_SERVICE)
        self.assertEqual(hass.calls[2]["data"]["command"], 0)
        self.assertEqual(hass.calls[2]["data"]["params"], {"attributes": [0]})


if __name__ == "__main__":
    unittest.main()
