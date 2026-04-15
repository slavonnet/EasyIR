"""Home Assistant wiring: room resolution, hub visibility, outbound logging."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import dispatcher
from homeassistant.helpers import entity_registry as er

from ..const import CONF_IEEE, CONF_VISIBLE_AREA_IDS, DOMAIN, TS1201_CLUSTER_ID
from ..helpers import DecodedIRPayload, decode_ir_payload_auto
from .event_log import IrEventLog, build_inbound_event, build_outbound_event

_LOGGER = logging.getLogger(__name__)

DATA_EVENT_LOG = "ir_event_log"
SIGNAL_INBOUND_DECODED = f"{DOMAIN}_inbound_decoded"


def get_domain_event_log(hass: HomeAssistant) -> IrEventLog:
    """Return the shared in-memory IR event log for this integration."""
    root = hass.data.setdefault(DOMAIN, {})
    log = root.get(DATA_EVENT_LOG)
    if log is None:
        log = IrEventLog()
        root[DATA_EVENT_LOG] = log
    return log  # type: ignore[return-value]


def hub_visible_room_ids_from_entry(entry_data: dict[str, Any]) -> frozenset[str] | None:
    """Parse optional hub room allow-list from config entry data."""
    raw = entry_data.get(CONF_VISIBLE_AREA_IDS)
    if not raw:
        return None
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        return frozenset(parts) if parts else None
    if isinstance(raw, (list, tuple, set)):
        return frozenset(str(x).strip() for x in raw if str(x).strip())
    return None


def _normalize_ieee(value: str) -> str:
    return value.lower().replace(" ", "")


def _entry_data_for_ieee(hass: HomeAssistant, ieee: str) -> dict[str, Any] | None:
    want = _normalize_ieee(ieee)
    for ent in hass.config_entries.async_entries(DOMAIN):
        current = _normalize_ieee(str(ent.data.get(CONF_IEEE, "")))
        if current == want:
            return dict(ent.data)
    return None


def _iter_payload_values(value: Any) -> Iterable[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, list, tuple)):
        return (value,)
    if isinstance(value, Mapping):
        out: list[Any] = []
        for key in ("code", "payload", "ir_code", "value", "raw"):
            candidate = value.get(key)
            if candidate is not None:
                out.append(candidate)
        return tuple(out)
    return ()


def _decode_zha_inbound_payload(event_data: Mapping[str, Any]) -> DecodedIRPayload | None:
    """Best-effort decode of raw IR payload from a zha_event dictionary."""
    candidates: list[Any] = []
    for key in ("params", "command_data", "args", "arguments"):
        value = event_data.get(key)
        if isinstance(value, (list, tuple)):
            for item in value:
                candidates.extend(_iter_payload_values(item))
        else:
            candidates.extend(_iter_payload_values(value))
    candidates.extend(_iter_payload_values(event_data))
    for payload in candidates:
        try:
            return decode_ir_payload_auto(payload)
        except ValueError:
            continue
    return None


def _easyir_device_id_for_ieee(hass: HomeAssistant, ieee: str) -> str | None:
    """Resolve EasyIR bridge device id from config IEEE (ZHA address)."""
    reg = dr.async_get(hass)
    want = _normalize_ieee(ieee)
    for device in reg.devices.values():
        for domain, ident in device.identifiers:
            if domain == DOMAIN and _normalize_ieee(str(ident)) == want:
                return device.id
    return None


def resolve_ieee_primary_area_id(hass: HomeAssistant, ieee: str) -> str | None:
    """Best-effort room (area) for the EasyIR hub device linked to this IEEE."""
    device_id = _easyir_device_id_for_ieee(hass, ieee)
    if device_id is None:
        return None
    reg = dr.async_get(hass)
    device = reg.async_get(device_id)
    if device is None or not device.area_id:
        return None
    return device.area_id


def resolve_entity_area_id(hass: HomeAssistant, entity_id: str) -> str | None:
    """Area id for an entity (via entity registry or device fallback)."""
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)
    if entry is None:
        return None
    if entry.area_id:
        return entry.area_id
    if entry.device_id:
        dev_reg = dr.async_get(hass)
        dev = dev_reg.async_get(entry.device_id)
        if dev is not None and dev.area_id:
            return dev.area_id
    return None


def log_outbound_send(
    hass: HomeAssistant,
    *,
    ieee: str,
    timings: list[int] | None,
    entity_id: str | None,
    entry_data: dict[str, Any],
    protocol_hint: str | None = None,
) -> None:
    """Append an outbound IR event after a successful send (non-blocking for callers)."""
    _ = entry_data  # reserved for future hub-only logging rules
    room_id = resolve_ieee_primary_area_id(hass, ieee)
    event_log = get_domain_event_log(hass)
    event_log.append(
        build_outbound_event(
            room_id=room_id,
            ieee=ieee,
            entity_id=entity_id,
            timings=timings,
            protocol_hint=protocol_hint,
            integrity_metadata={"source": "easyir.send"},
        )
    )
    _LOGGER.debug(
        "Logged outbound IR event ieee=%s room=%s entity=%s",
        ieee,
        room_id,
        entity_id,
    )


@callback
def async_setup_inbound_listener(hass: HomeAssistant) -> None:
    """Listen for decoded inbound signals and apply room-scoped sync (once)."""
    if hass.data.get(DOMAIN, {}).get("_inbound_listener_ready"):
        return
    hass.data.setdefault(DOMAIN, {})["_inbound_listener_ready"] = True

    from .sync import SyncTarget, apply_inbound_decoded_signal

    def _apply_decoded(target_entity_id: str, decoded: dict[str, Any]) -> None:
        entities = hass.data.get(DOMAIN, {}).get("climate_entities", {})
        entity = entities.get(target_entity_id)
        if entity is None:
            return
        handler = getattr(entity, "async_handle_easyir_inbound_decoded", None)
        if callable(handler):
            handler(decoded)

    @callback
    def _on_inbound(event: dict[str, Any]) -> None:
        ieee = event.get("ieee")
        if not ieee:
            return
        entry_data = _entry_data_for_ieee(hass, str(ieee))
        if entry_data is None:
            return

        hub_rooms = hub_visible_room_ids_from_entry(entry_data)
        event_room = event.get("room_id")
        if event_room is None:
            event_room = resolve_ieee_primary_area_id(hass, str(ieee))

        decoded = event.get("decoded_state")
        if not isinstance(decoded, dict):
            return

        decoded_device_id = event.get("decoded_device_id")
        if decoded_device_id is not None:
            decoded_device_id = str(decoded_device_id)

        ent_reg = er.async_get(hass)
        targets: list[SyncTarget] = []
        for e in ent_reg.entities.values():
            if e.platform != DOMAIN or e.domain != "climate":
                continue
            device_id = e.device_id
            area = resolve_entity_area_id(hass, e.entity_id)
            targets.append(
                SyncTarget(
                    entity_id=e.entity_id,
                    area_id=area,
                    device_id=device_id,
                )
            )

        suggestions: list[dict[str, Any]] = []

        def _suggest(payload: dict[str, Any]) -> None:
            suggestions.append(payload)

        apply_inbound_decoded_signal(
            event_room_id=event_room if isinstance(event_room, str) else None,
            ieee=str(ieee),
            decoded_state=decoded,
            decoded_device_id=decoded_device_id,
            targets=targets,
            hub_visible_room_ids=hub_rooms,
            apply_decoded=_apply_decoded,
            event_log=get_domain_event_log(hass),
            timings=event.get("timings") if isinstance(event.get("timings"), list) else None,
            protocol_hint=event.get("protocol_hint")
            if isinstance(event.get("protocol_hint"), str)
            else None,
            suggest_unknown=_suggest,
            integrity_metadata={"source": "dispatcher"},
        )

        for payload in suggestions:
            hass.bus.async_fire(
                f"{DOMAIN}_suggest_add_device",
                payload,
            )

    @callback
    def _on_zha_event(event: Event) -> None:
        """Capture inbound IR payloads from ZHA events for Signal Log."""
        data = event.data if isinstance(event.data, Mapping) else {}
        async_handle_zha_event_for_easyir(hass, data)

    dispatcher.async_dispatcher_connect(hass, SIGNAL_INBOUND_DECODED, _on_inbound)
    hass.bus.async_listen("zha_event", _on_zha_event)


@callback
def async_fire_inbound_decoded(hass: HomeAssistant, payload: dict[str, Any]) -> None:
    """Fire internal inbound-decoded event for room-scoped sync (transport / ZHA hooks)."""
    dispatcher.async_dispatcher_send(hass, SIGNAL_INBOUND_DECODED, payload)


@callback
def async_handle_zha_event_for_easyir(
    hass: HomeAssistant, event_data: Mapping[str, Any]
) -> bool:
    """Decode supported ZHA inbound payload and append it to EasyIR Signal Log."""
    cluster_id = event_data.get("cluster_id")
    if cluster_id is not None:
        try:
            if int(cluster_id) != TS1201_CLUSTER_ID:
                return False
        except (TypeError, ValueError):
            return False

    ieee_raw = event_data.get("device_ieee") or event_data.get("ieee")
    if not isinstance(ieee_raw, str) or not ieee_raw.strip():
        return False
    ieee = ieee_raw.strip()
    entry_data = _entry_data_for_ieee(hass, ieee)
    if entry_data is None:
        return False

    decoded_payload = _decode_zha_inbound_payload(event_data)
    if decoded_payload is None:
        return False

    room_id = resolve_ieee_primary_area_id(hass, ieee)
    get_domain_event_log(hass).append(
        build_inbound_event(
            room_id=room_id,
            ieee=ieee,
            timings=decoded_payload.raw_timings,
            protocol_hint=decoded_payload.source_encoding,
            integrity_metadata={
                "source": "zha_event",
                "cluster_id": event_data.get("cluster_id"),
                "command": event_data.get("command"),
                "entry_has_room_filter": bool(hub_visible_room_ids_from_entry(entry_data)),
            },
        )
    )
    return True
