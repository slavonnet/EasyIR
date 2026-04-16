"""Tests for signal log pagination and HTTP query parsing / serialization."""

from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import make_mocked_request

REPO_ROOT = Path(__file__).resolve().parent.parent
EASYIR_ROOT = REPO_ROOT / "custom_components" / "easyir"
sys.path.insert(0, str(EASYIR_ROOT))

from const import DOMAIN  # noqa: E402
from signal_log.event_log import (  # noqa: E402
    IrEventDirection,
    IrEventLog,
    build_inbound_event,
    build_outbound_event,
)

DATA_EVENT_LOG = "ir_event_log"


class TestIrEventLogPagination(unittest.TestCase):
    def test_room_filter_and_offset_newest_first(self) -> None:
        log = IrEventLog(max_events=50)
        for rid, direction in (
            ("kitchen", IrEventDirection.OUTBOUND),
            ("living", IrEventDirection.INBOUND),
            ("living", IrEventDirection.OUTBOUND),
        ):
            log.append(
                build_outbound_event(
                    room_id=rid,
                    ieee="x",
                    entity_id=None,
                    timings=[1, 2],
                    protocol_hint="p",
                )
                if direction == IrEventDirection.OUTBOUND
                else build_inbound_event(
                    room_id=rid,
                    ieee="x",
                    timings=[3, 4],
                    protocol_hint="p",
                )
            )
        rows = list(
            log.iter_events(room_id="living", limit=10, offset=0, direction=None)
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].direction, IrEventDirection.OUTBOUND)
        self.assertEqual(rows[1].direction, IrEventDirection.INBOUND)

        page2 = list(
            log.iter_events(room_id="living", limit=1, offset=1, direction=None)
        )
        self.assertEqual(len(page2), 1)
        self.assertEqual(page2[0].direction, IrEventDirection.INBOUND)

    def test_direction_filter(self) -> None:
        log = IrEventLog(max_events=20)
        log.append(
            build_inbound_event(
                room_id="r1", ieee="a", timings=[1], protocol_hint=None
            )
        )
        log.append(
            build_outbound_event(
                room_id="r1", ieee="a", entity_id=None, timings=[2], protocol_hint=None
            )
        )
        only_out = list(
            log.iter_events(
                room_id="r1", direction=IrEventDirection.OUTBOUND, limit=10, offset=0
            )
        )
        self.assertEqual(len(only_out), 1)
        self.assertEqual(only_out[0].direction, IrEventDirection.OUTBOUND)


class TestSignalLogQueryParsing(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.hass = __import__(
            "homeassistant.core", fromlist=["HomeAssistant"]
        ).HomeAssistant("/tmp/easyir_signal_log_test")

    async def asyncTearDown(self) -> None:
        await self.hass.async_stop(force=True)

    async def test_events_view_returns_filtered_json(self) -> None:
        api = importlib.import_module("custom_components.easyir.signal_log.api")
        from homeassistant.components import http

        log = self.hass.data.setdefault(DOMAIN, {})[DATA_EVENT_LOG] = IrEventLog(
            max_events=20
        )
        log.append(
            build_outbound_event(
                room_id="area_a",
                ieee="aa:bb",
                entity_id=None,
                timings=[100, 200],
                protocol_hint="raw_timings",
            )
        )
        log.append(
            build_outbound_event(
                room_id="area_b",
                ieee="cc:dd",
                entity_id=None,
                timings=[1, 2],
                protocol_hint="profile",
            )
        )

        app = {http.KEY_HASS: self.hass}
        request = make_mocked_request(
            "GET",
            "/api/easyir/signal_log/events?room_id=area_a&limit=5&offset=0",
            app=app,
        )
        view = api.EasyIrSignalLogEventsView()
        response = view.get(request)
        self.assertEqual(response.status, 200)
        payload = json.loads(response.body.decode())
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["events"][0]["room_id"], "area_a")
        self.assertFalse(payload["has_more"])
        self.assertEqual(payload["limit"], 5)
        self.assertEqual(payload["offset"], 0)

    async def test_events_view_has_more_pagination(self) -> None:
        api = importlib.import_module("custom_components.easyir.signal_log.api")
        from homeassistant.components import http

        log = self.hass.data.setdefault(DOMAIN, {})[DATA_EVENT_LOG] = IrEventLog(
            max_events=20
        )
        for i in range(3):
            log.append(
                build_inbound_event(
                    room_id="r",
                    ieee="z",
                    timings=[i],
                    protocol_hint="x",
                )
            )

        app = {http.KEY_HASS: self.hass}
        r1 = make_mocked_request(
            "GET",
            "/api/easyir/signal_log/events?room_id=r&limit=2&offset=0",
            app=app,
        )
        view = api.EasyIrSignalLogEventsView()
        p1 = json.loads(view.get(r1).body.decode())
        self.assertEqual(len(p1["events"]), 2)
        self.assertTrue(p1["has_more"])

        r2 = make_mocked_request(
            "GET",
            "/api/easyir/signal_log/events?room_id=r&limit=2&offset=2",
            app=app,
        )
        p2 = json.loads(view.get(r2).body.decode())
        self.assertEqual(len(p2["events"]), 1)
        self.assertFalse(p2["has_more"])

    async def test_invalid_direction_400(self) -> None:
        api = importlib.import_module("custom_components.easyir.signal_log.api")
        from homeassistant.components import http

        self.hass.data.setdefault(DOMAIN, {})[DATA_EVENT_LOG] = IrEventLog()
        app = {http.KEY_HASS: self.hass}
        request = make_mocked_request(
            "GET",
            "/api/easyir/signal_log/events?direction=sideways",
            app=app,
        )
        view = api.EasyIrSignalLogEventsView()
        response = view.get(request)
        self.assertEqual(response.status, 400)

    async def test_start_learn_view_invokes_start_ir_learning(self) -> None:
        api = importlib.import_module("custom_components.easyir.signal_log.api")
        from homeassistant.components import http

        self.hass.config_entries = type(
            "Cfg",
            (),
            {"async_entries": lambda _self, _domain: [object()]},
        )()
        app = {http.KEY_HASS: self.hass}
        request = make_mocked_request(
            "POST",
            "/api/easyir/signal_log/start_learn",
            app=app,
            headers={"Content-Type": "application/json"},
        )
        request._read_bytes = json.dumps(
            {"ieee": "aa:bb:cc:dd:ee:ff", "endpoint_id": 2, "timeout_s": 12}
        ).encode()
        view = api.EasyIrSignalLogStartLearnView()
        with patch(
            "custom_components.easyir.signal_log.api.async_detect_ir_learn_profile",
            new=AsyncMock(return_value="ts1201_zosung"),
        ) as detect_mock, patch(
            "custom_components.easyir.signal_log.api.async_start_ir_learning",
            new=AsyncMock(return_value={"status": "learning", "vendor_profile": "ts1201_zosung"}),
        ) as start_mock:
            response = await view.post(request)
        self.assertEqual(response.status, 200)
        payload = json.loads(response.body.decode())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["vendor_profile"], "ts1201_zosung")
        detect_mock.assert_awaited_once_with(self.hass, "aa:bb:cc:dd:ee:ff")
        start_mock.assert_awaited_once_with(
            self.hass,
            ieee="aa:bb:cc:dd:ee:ff",
            endpoint_id=2,
            vendor_profile="ts1201_zosung",
            timeout_s=12,
        )

    async def test_start_learn_view_rejects_invalid_endpoint(self) -> None:
        api = importlib.import_module("custom_components.easyir.signal_log.api")
        from homeassistant.components import http

        app = {http.KEY_HASS: self.hass}
        request = make_mocked_request(
            "POST",
            "/api/easyir/signal_log/start_learn",
            app=app,
            headers={"Content-Type": "application/json"},
        )
        request._read_bytes = json.dumps(
            {"ieee": "aa:bb:cc:dd:ee:ff", "endpoint_id": 0}
        ).encode()
        view = api.EasyIrSignalLogStartLearnView()
        response = await view.post(request)
        self.assertEqual(response.status, 400)
        payload = json.loads(response.body.decode())
        self.assertIn("endpoint_id", payload["message"])


if __name__ == "__main__":
    unittest.main()
