"""HTTP API for room-scoped IR signal log (sidebar Signal Log tool backend)."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components import http
from homeassistant.core import HomeAssistant, callback

from ..const import DOMAIN
from .event_log import IrEvent, IrEventDirection
from .ha_bridge import get_domain_event_log


def _serialize_event(ev: IrEvent) -> dict[str, Any]:
    return {
        "event_id": ev.event_id,
        "direction": ev.direction.value,
        "recorded_at": ev.recorded_at.isoformat(),
        "room_id": ev.room_id,
        "ieee": ev.ieee,
        "entity_id": ev.entity_id,
        "carrier_frequency_hz": ev.carrier_frequency_hz,
        "timings": ev.timings,
        "repeat": ev.repeat,
        "duty_cycle": ev.duty_cycle,
        "protocol_hint": ev.protocol_hint,
        "integrity_metadata": ev.integrity_metadata,
        "decoded": ev.decoded,
    }


QUERY_SCHEMA = vol.Schema(
    {
        vol.Optional("limit", default=50): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=200)
        ),
        vol.Optional("offset", default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)


def _parse_query(request: web.Request) -> dict[str, Any]:
    q = request.rel_url.query
    room_raw = q.get("room_id")
    room_id: str | None
    if room_raw is None:
        room_id = None
    else:
        room_id = str(room_raw).strip() or None

    dir_raw = q.get("direction")
    if dir_raw is None or str(dir_raw).strip() == "":
        dir_enum: IrEventDirection | None = None
    else:
        low = str(dir_raw).strip().lower()
        if low == "inbound":
            dir_enum = IrEventDirection.INBOUND
        elif low == "outbound":
            dir_enum = IrEventDirection.OUTBOUND
        else:
            raise vol.Invalid("direction must be inbound or outbound")

    data = QUERY_SCHEMA(
        {
            "limit": q.get("limit"),
            "offset": q.get("offset"),
        }
    )
    return {
        "room_id": room_id,
        "direction": dir_enum,
        "limit": data["limit"],
        "offset": data["offset"],
    }


class EasyIrSignalLogEventsView(http.HomeAssistantView):
    """JSON list of signal log events (newest first) with optional room/direction filter."""

    url = "/api/easyir/signal_log/events"
    name = "api:easyir:signal_log:events"
    requires_auth = True

    @callback
    def get(self, request: web.Request) -> web.Response:
        """Return a page of events from the in-memory log."""
        hass: HomeAssistant = request.app[http.KEY_HASS]
        try:
            params = _parse_query(request)
        except vol.Invalid as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)

        log = get_domain_event_log(hass)
        room_id = params["room_id"]
        direction = params["direction"]
        limit = params["limit"]
        offset = params["offset"]

        events = list(
            log.iter_events(
                room_id=room_id,
                direction=direction,
                limit=limit,
                offset=offset,
            )
        )
        peek = next(
            iter(
                log.iter_events(
                    room_id=room_id,
                    direction=direction,
                    limit=1,
                    offset=offset + limit,
                )
            ),
            None,
        )
        has_more = peek is not None

        return self.json(
            {
                "events": [_serialize_event(ev) for ev in events],
                "has_more": has_more,
                "limit": limit,
                "offset": offset,
            }
        )


class EasyIrSignalLogPageView(http.HomeAssistantView):
    """Minimal HTML tool page for the Signal Log (loads data from JSON API)."""

    url = "/api/easyir/signal_log/page"
    name = "api:easyir:signal_log:page"
    requires_auth = True

    @callback
    def get(self, request: web.Request) -> web.Response:
        """Serve a small standalone page (iframe-friendly)."""
        hass: HomeAssistant = request.app[http.KEY_HASS]
        if not hass.config_entries.async_entries(DOMAIN):
            body = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'><title>EasyIR Signal Log</title>"
                "</head><body><p>EasyIR is not configured.</p></body></html>"
            )
            return web.Response(
                text=body,
                content_type="text/html",
                charset="utf-8",
                status=HTTPStatus.OK,
            )

        # Inline minimal UI; fetches same-origin JSON API with session cookies.
        body = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>EasyIR Signal Log</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 1rem; }
    label { margin-right: 0.5rem; }
    input, select, button { margin: 0.25rem 0.5rem 0.25rem 0; }
    table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
    th, td { border: 1px solid #ccc; padding: 0.35rem 0.5rem; text-align: left; font-size: 0.85rem; }
    th { background: #f4f4f4; }
    .muted { color: #666; font-size: 0.8rem; }
  </style>
</head>
<body>
  <h2>EasyIR Signal Log</h2>
  <div>
    <label>Room (area id)</label>
    <input id="room" type="text" placeholder="optional — filter by hub room"/>
    <label>Direction</label>
    <select id="dir">
      <option value="">all</option>
      <option value="inbound">inbound</option>
      <option value="outbound">outbound</option>
    </select>
    <label>Limit</label>
    <input id="limit" type="number" value="50" min="1" max="200"/>
    <button type="button" id="load">Load</button>
    <button type="button" id="more">Older page</button>
  </div>
  <p class="muted" id="status"></p>
  <table>
    <thead><tr>
      <th>Time (UTC)</th><th>Dir</th><th>Room</th><th>IEEE</th><th>Protocol</th><th>Decoded</th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <script>
    const api = "/api/easyir/signal_log/events";
    let offset = 0;
    function qs() {
      const room = document.getElementById("room").value.trim();
      const dir = document.getElementById("dir").value;
      const limit = document.getElementById("limit").value || "50";
      const p = new URLSearchParams({ limit, offset: String(offset) });
      if (room) p.set("room_id", room);
      if (dir) p.set("direction", dir);
      return p.toString();
    }
    async function fetchPage(append) {
      const st = document.getElementById("status");
      st.textContent = "Loading…";
      const res = await fetch(api + "?" + qs(), { credentials: "same-origin" });
      if (!res.ok) {
        st.textContent = "Error " + res.status;
        return;
      }
      const data = await res.json();
      const tbody = document.getElementById("rows");
      if (!append) tbody.innerHTML = "";
      for (const ev of data.events) {
        const tr = document.createElement("tr");
        const dec = ev.decoded ? JSON.stringify(ev.decoded) : "";
        tr.innerHTML = "<td>" + ev.recorded_at + "</td><td>" + ev.direction + "</td><td>"
          + (ev.room_id || "") + "</td><td>" + (ev.ieee || "") + "</td><td>"
          + (ev.protocol_hint || "") + "</td><td>" + dec + "</td>";
        tbody.appendChild(tr);
      }
      st.textContent = data.events.length + " events" + (data.has_more ? " (more available)" : "");
      document.getElementById("more").disabled = !data.has_more;
    }
    document.getElementById("load").onclick = () => { offset = 0; fetchPage(false); };
    document.getElementById("more").onclick = () => {
      const lim = parseInt(document.getElementById("limit").value || "50", 10);
      offset += lim;
      fetchPage(true);
    };
    offset = 0;
    fetchPage(false);
  </script>
</body>
</html>"""
        return web.Response(
            text=body,
            content_type="text/html",
            charset="utf-8",
            status=HTTPStatus.OK,
        )


@callback
def async_register_signal_log_api(hass: HomeAssistant) -> None:
    """Register HTTP views once (idempotent)."""
    root = hass.data.setdefault(DOMAIN, {})
    if root.get("_signal_log_api_registered"):
        return
    hass.http.register_view(EasyIrSignalLogEventsView)
    hass.http.register_view(EasyIrSignalLogPageView)
    root["_signal_log_api_registered"] = True
