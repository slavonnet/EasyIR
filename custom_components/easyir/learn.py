"""IR learn-mode control and payload readback per hub profile."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceNotFound
from homeassistant.helpers import device_registry as dr

from .command_pool import async_call_pooled_service
from .const import (
    CONF_IEEE,
    CONF_HUB_ID,
    DEFAULT_ENDPOINT_ID,
    DOMAIN,
    IR_LEARN_ATTRIBUTE_ID,
    TS1201_CLUSTER_ID,
    TS1201_CLUSTER_TYPE,
    TS1201_COMMAND_TYPE,
    TS1201_IRLEARN_COMMAND_ID,
    TS1201_LAST_LEARNED_ATTR_ID,
    EVENT_LEARN_TRACE,
    ZHA_DOMAIN,
    ZHA_SERVICE,
)

VENDOR_PROFILE_TS1201_ZOSUNG = "ts1201_zosung"
_LOGGER = logging.getLogger(__name__)
_READ_ATTR_SERVICE = "read_zigbee_cluster_attributes"


def _emit_learn_trace_event(hass: HomeAssistant, payload: dict[str, Any]) -> None:
    """Emit optional debug event if hass bus is available."""
    bus = getattr(hass, "bus", None)
    if bus is None or not hasattr(bus, "async_fire"):
        return
    bus.async_fire(EVENT_LEARN_TRACE, payload)


@dataclass(frozen=True, slots=True)
class LearnProfile:
    """Learn-mode behavior for a specific IR hub model."""

    profile_id: str
    cluster_id: int
    learn_command_id: int
    read_attr_id: int
    explicit_stop_supported: bool
    timeout_s: float


TS1201_LEARN_PROFILE = LearnProfile(
    profile_id=VENDOR_PROFILE_TS1201_ZOSUNG,
    cluster_id=TS1201_CLUSTER_ID,
    learn_command_id=TS1201_IRLEARN_COMMAND_ID,
    read_attr_id=TS1201_LAST_LEARNED_ATTR_ID,
    explicit_stop_supported=False,
    timeout_s=35.0,
)


def _normalize_ieee(value: str) -> str:
    return value.lower().replace(" ", "")


def _entry_for_ieee(hass: HomeAssistant, ieee: str) -> dict[str, Any] | None:
    want = _normalize_ieee(ieee)
    for entry in hass.config_entries.async_entries(DOMAIN):
        current = _normalize_ieee(str(entry.data.get(CONF_IEEE, "")))
        if current == want:
            return dict(entry.data)
    return None


def _entry_for_hub_id(hass: HomeAssistant, hub_id: str) -> dict[str, Any] | None:
    """Return config entry data for a specific EasyIR hub entry id."""
    target = str(hub_id).strip()
    if not target:
        return None
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == target:
            return dict(entry.data)
    return None


def _entry_endpoint_id(entry_data: dict[str, Any] | None) -> int:
    if not entry_data:
        return DEFAULT_ENDPOINT_ID
    try:
        return int(entry_data.get("endpoint_id", DEFAULT_ENDPOINT_ID))
    except (TypeError, ValueError):
        return DEFAULT_ENDPOINT_ID


async def async_resolve_learn_target(
    hass: HomeAssistant,
    *,
    hub_id: str | None = None,
    ieee: str | None = None,
    endpoint_id: int | None = None,
) -> dict[str, Any]:
    """Resolve learn target from hub_id/ieee and detect vendor-specific profile."""
    entry_data_by_hub: dict[str, Any] | None = None
    if hub_id is not None and str(hub_id).strip():
        entry_data_by_hub = _entry_for_hub_id(hass, str(hub_id))
        if entry_data_by_hub is None:
            raise ValueError(f"Unknown EasyIR hub_id: {hub_id}")

    resolved_ieee = str(ieee or "").strip() or None
    if entry_data_by_hub is not None:
        hub_ieee = str(entry_data_by_hub.get(CONF_IEEE, "")).strip() or None
        if resolved_ieee and hub_ieee:
            if _normalize_ieee(resolved_ieee) != _normalize_ieee(hub_ieee):
                raise ValueError("hub_id and ieee refer to different hubs")
        if resolved_ieee is None:
            resolved_ieee = hub_ieee

    if not resolved_ieee:
        raise ValueError("Learn target is required: provide hub_id or ieee")

    if endpoint_id is None:
        entry_data = entry_data_by_hub or _entry_for_ieee(hass, resolved_ieee)
        resolved_endpoint_id = _entry_endpoint_id(entry_data)
    else:
        resolved_endpoint_id = int(endpoint_id)

    vendor_profile = await async_detect_ir_learn_profile(hass, resolved_ieee)
    if vendor_profile is None:
        raise ValueError("No supported learn profile for this IR hub")

    return {
        CONF_HUB_ID: str(hub_id).strip() if hub_id else None,
        CONF_IEEE: resolved_ieee,
        "endpoint_id": resolved_endpoint_id,
        "vendor_profile": vendor_profile,
    }


async def _issue_irlearn(hass: HomeAssistant, ieee: str, endpoint_id: int, on: bool) -> None:
    payload = {
        "ieee": ieee,
        "endpoint_id": endpoint_id,
        "cluster_id": TS1201_CLUSTER_ID,
        "cluster_type": TS1201_CLUSTER_TYPE,
        "command": TS1201_IRLEARN_COMMAND_ID,
        "command_type": TS1201_COMMAND_TYPE,
        "params": {"on_off": bool(on)},
    }
    _LOGGER.debug(
        "easyir.learn_trace stage=issue_irlearn_prepare ieee=%s endpoint_id=%s on=%s payload=%s",
        ieee,
        endpoint_id,
        bool(on),
        payload,
    )
    _emit_learn_trace_event(
        hass,
        {
            "stage": "issue_irlearn_prepare",
            "ieee": ieee,
            "endpoint_id": endpoint_id,
            "on": bool(on),
            "payload": payload,
        },
    )
    await async_call_pooled_service(
        hass,
        ieee=ieee,
        domain=ZHA_DOMAIN,
        service=ZHA_SERVICE,
        data=payload,
        return_response=False,
        dedupe=False,
        priority=0,
    )
    _LOGGER.debug(
        "easyir.learn_trace stage=issue_irlearn_sent ieee=%s endpoint_id=%s on=%s",
        ieee,
        endpoint_id,
        bool(on),
    )
    _emit_learn_trace_event(
        hass,
        {
            "stage": "issue_irlearn_sent",
            "ieee": ieee,
            "endpoint_id": endpoint_id,
            "on": bool(on),
        },
    )


def _service_is_available(hass: HomeAssistant, domain: str, service: str) -> bool:
    """Best-effort service availability check, tolerant of test doubles."""
    services = getattr(hass, "services", None)
    has_service = getattr(services, "has_service", None)
    if not callable(has_service):
        # Unknown runtime stub; keep legacy behavior and attempt the call.
        return True
    try:
        return bool(has_service(domain, service))
    except Exception:
        return True


def _is_missing_service_error(err: Exception) -> bool:
    """Return True when the exception indicates a missing HA service."""
    if isinstance(err, ServiceNotFound):
        return True
    text = f"{type(err).__name__}: {err}".lower()
    if "servicenotfound" in text:
        return True
    if "service not found" in text:
        return True
    return "action" in text and "not found" in text


async def _read_last_learned_via_issue_command(
    hass: HomeAssistant, ieee: str, endpoint_id: int
) -> Any:
    return await async_call_pooled_service(
        hass,
        ieee=ieee,
        domain=ZHA_DOMAIN,
        service=ZHA_SERVICE,
        data={
            "ieee": ieee,
            "endpoint_id": endpoint_id,
            "cluster_id": TS1201_CLUSTER_ID,
            "cluster_type": TS1201_CLUSTER_TYPE,
            "command": 0,
            "command_type": TS1201_COMMAND_TYPE,
            "params": {"attributes": [TS1201_LAST_LEARNED_ATTR_ID]},
        },
        return_response=True,
        dedupe=False,
        priority=1,
    )


def _extract_attr_string(result: Any, attr_id: int) -> str | None:
    if not isinstance(result, dict):
        return None
    for container_name in ("success", "response"):
        container = result.get(container_name)
        if not isinstance(container, dict):
            continue
        for key in (attr_id, str(attr_id), f"0x{attr_id:04X}"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


async def _read_last_learned(hass: HomeAssistant, ieee: str, endpoint_id: int) -> str | None:
    payload = {
        "ieee": ieee,
        "endpoint_id": endpoint_id,
        "cluster_id": TS1201_CLUSTER_ID,
        "cluster_type": TS1201_CLUSTER_TYPE,
        "attribute": [TS1201_LAST_LEARNED_ATTR_ID],
    }
    if _service_is_available(hass, ZHA_DOMAIN, _READ_ATTR_SERVICE):
        try:
            result = await async_call_pooled_service(
                hass,
                ieee=ieee,
                domain=ZHA_DOMAIN,
                service=_READ_ATTR_SERVICE,
                data=payload,
                return_response=True,
                dedupe=False,
                priority=1,
            )
        except Exception as err:
            # HA/ZHA versions differ: some don't expose read-zigbee-attributes API.
            # Fall back to generic issue_zigbee_cluster_command read-attributes.
            if not _is_missing_service_error(err):
                raise
            _LOGGER.debug(
                "Learn read fallback: service %s is unavailable (%s), using %s",
                _READ_ATTR_SERVICE,
                err,
                ZHA_SERVICE,
            )
            result = await _read_last_learned_via_issue_command(
                hass, ieee, endpoint_id
            )
    else:
        result = await _read_last_learned_via_issue_command(hass, ieee, endpoint_id)
    return _extract_attr_string(result, TS1201_LAST_LEARNED_ATTR_ID)


async def _read_last_learned_legacy(hass: HomeAssistant, ieee: str, endpoint_id: int) -> str | None:
    """Legacy parser left for safety while migrating helpers."""
    result = await async_call_pooled_service(
            hass,
            ieee=ieee,
            domain=ZHA_DOMAIN,
            service=_READ_ATTR_SERVICE,
            data=payload,
            return_response=True,
            dedupe=False,
            priority=1,
        )
    if not isinstance(result, dict):
        return None
    success = result.get("success")
    if not isinstance(success, dict):
        return None
    value = success.get(TS1201_LAST_LEARNED_ATTR_ID)
    if value is None:
        value = success.get(str(TS1201_LAST_LEARNED_ATTR_ID))
    if value is None:
        value = success.get(f"0x{TS1201_LAST_LEARNED_ATTR_ID:04X}")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


class Ts1201LearnAdapter:
    """Model-specific learn-mode implementation for Tuya/Zosung TS1201."""

    async def async_start_learning(
        self,
        hass: HomeAssistant,
        ieee: str,
        *,
        timeout_s: int = 30,
        endpoint_id: int = DEFAULT_ENDPOINT_ID,
    ) -> dict[str, Any]:
        await _issue_irlearn(hass, ieee, endpoint_id, True)
        return {
            "status": "learning",
            "vendor_profile": VENDOR_PROFILE_TS1201_ZOSUNG,
            "timeout_s": int(timeout_s),
        }

    async def async_stop_learning(
        self,
        hass: HomeAssistant,
        ieee: str,
        *,
        endpoint_id: int = DEFAULT_ENDPOINT_ID,
    ) -> dict[str, Any]:
        # Real-world TS1201 variants can re-enter learn mode on `on_off=false`.
        # Do not send explicit stop command; rely on device auto-exit behavior.
        _ = (hass, ieee, endpoint_id)
        return {
            "status": "auto_stop_expected",
            "vendor_profile": VENDOR_PROFILE_TS1201_ZOSUNG,
        }

    async def async_read_learned_code(
        self,
        hass: HomeAssistant,
        ieee: str,
        *,
        endpoint_id: int = DEFAULT_ENDPOINT_ID,
    ) -> dict[str, Any]:
        code = await _read_last_learned(hass, ieee, endpoint_id)
        if not code:
            raise ValueError("No learned IR code available")
        return {
            "code": code,
            "attribute_id": IR_LEARN_ATTRIBUTE_ID,
            "vendor_profile": VENDOR_PROFILE_TS1201_ZOSUNG,
        }


async def async_detect_ir_learn_profile(
    hass: HomeAssistant, ieee: str
) -> str | None:
    """Detect vendor learn profile by hub model (extensible for multiple IR hubs)."""
    want = _normalize_ieee(ieee)
    try:
        reg = dr.async_get(hass)
        for dev in reg.devices.values():
            model = (getattr(dev, "model", None) or "").strip().upper()
            model_id = (getattr(dev, "model_id", None) or "").strip().upper()
            if model == "TS1201" or model_id == "TS1201":
                identifiers = getattr(dev, "identifiers", None) or ()
                if not identifiers:
                    return VENDOR_PROFILE_TS1201_ZOSUNG
                for _, ident in identifiers:
                    if _normalize_ieee(str(ident)) == want:
                        return VENDOR_PROFILE_TS1201_ZOSUNG
    except Exception:
        # Unit-test fakes may not provide a full HA storage-backed registry.
        pass
    if _entry_for_ieee(hass, ieee) is not None:
        return VENDOR_PROFILE_TS1201_ZOSUNG
    return None


async def async_start_ir_learning(
    hass: HomeAssistant,
    *,
    ieee: str,
    vendor_profile: str,
    endpoint_id: int | None = None,
    timeout_s: int = 30,
) -> dict[str, Any]:
    """Start learn mode for one hub according to vendor profile implementation."""
    if vendor_profile != VENDOR_PROFILE_TS1201_ZOSUNG:
        raise ValueError(f"Unsupported learn vendor profile: {vendor_profile}")
    entry_data = _entry_for_ieee(hass, ieee)
    resolved_endpoint_id = (
        int(endpoint_id) if endpoint_id is not None else _entry_endpoint_id(entry_data)
    )
    adapter = Ts1201LearnAdapter()
    return await adapter.async_start_learning(
        hass,
        ieee,
        timeout_s=timeout_s,
        endpoint_id=resolved_endpoint_id,
    )


async def async_stop_ir_learning(
    hass: HomeAssistant,
    *,
    ieee: str,
    vendor_profile: str,
) -> dict[str, Any]:
    """Stop learn mode for one hub."""
    if vendor_profile != VENDOR_PROFILE_TS1201_ZOSUNG:
        raise ValueError(f"Unsupported learn vendor profile: {vendor_profile}")
    entry_data = _entry_for_ieee(hass, ieee)
    adapter = Ts1201LearnAdapter()
    return await adapter.async_stop_learning(
        hass,
        ieee,
        endpoint_id=_entry_endpoint_id(entry_data),
    )


def _extract_learn_attr_code(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    response = result.get("response")
    if isinstance(response, dict):
        for key in (
            IR_LEARN_ATTRIBUTE_ID,
            str(IR_LEARN_ATTRIBUTE_ID),
            f"0x{IR_LEARN_ATTRIBUTE_ID:04X}",
        ):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    success = result.get("success")
    if isinstance(success, dict):
        for key in (
            IR_LEARN_ATTRIBUTE_ID,
            str(IR_LEARN_ATTRIBUTE_ID),
            f"0x{IR_LEARN_ATTRIBUTE_ID:04X}",
        ):
            value = success.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


async def async_list_configured_learn_hubs(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return configured EasyIR hubs suitable for learn operations."""
    hubs: list[dict[str, Any]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        data = dict(entry.data)
        ieee = str(data.get(CONF_IEEE, "")).strip()
        if not ieee:
            continue
        vendor_profile = await async_detect_ir_learn_profile(hass, ieee)
        if vendor_profile is None:
            continue
        hubs.append(
            {
                "hub_id": entry.entry_id,
                "title": entry.title,
                "ieee": ieee,
                "endpoint_id": _entry_endpoint_id(data),
                "vendor_profile": vendor_profile,
            }
        )
    hubs.sort(key=lambda item: (str(item["title"]).lower(), str(item["hub_id"])))
    return hubs


async def async_read_learned_ir_code(
    hass: HomeAssistant,
    *,
    ieee: str,
    vendor_profile: str,
) -> dict[str, Any]:
    """Read last learned code attribute according to vendor profile."""
    if vendor_profile != VENDOR_PROFILE_TS1201_ZOSUNG:
        raise ValueError(f"Unsupported learn vendor profile: {vendor_profile}")
    entry_data = _entry_for_ieee(hass, ieee)
    endpoint_id = _entry_endpoint_id(entry_data)
    result = await async_call_pooled_service(
        hass,
        ieee=ieee,
        domain=ZHA_DOMAIN,
        service=ZHA_SERVICE,
        data={
            "ieee": ieee,
            "endpoint_id": endpoint_id,
            "cluster_id": TS1201_CLUSTER_ID,
            "cluster_type": TS1201_CLUSTER_TYPE,
            "command": 0,
            "command_type": TS1201_COMMAND_TYPE,
            "params": {"attributes": [IR_LEARN_ATTRIBUTE_ID]},
        },
        return_response=True,
        dedupe=False,
        priority=1,
    )
    code = _extract_learn_attr_code(result)
    if not code:
        raise ValueError("Learned IR code attribute is empty")
    return {
        "code": code,
        "attribute_id": IR_LEARN_ATTRIBUTE_ID,
        "vendor_profile": VENDOR_PROFILE_TS1201_ZOSUNG,
    }


async def learn_once(
    hass: HomeAssistant,
    *,
    ieee: str | None = None,
    hub_id: str | None = None,
    endpoint_id: int | None = None,
    timeout_s: int,
    poll_interval_s: float = 0.8,
) -> dict[str, Any]:
    """
    Learn one IR payload from a hub-specific learn profile.

    For TS1201:
    - enable IRLearn,
    - poll last learned attribute,
    - disable IRLearn on success/timeout/failure.
    """
    resolved_target = await async_resolve_learn_target(
        hass,
        hub_id=hub_id,
        ieee=ieee,
        endpoint_id=endpoint_id,
    )
    resolved_ieee = str(resolved_target[CONF_IEEE])
    resolved_endpoint_id = int(resolved_target["endpoint_id"])
    vendor_profile = str(resolved_target["vendor_profile"])
    if vendor_profile != VENDOR_PROFILE_TS1201_ZOSUNG:
        raise ValueError(f"Unsupported learn vendor profile: {vendor_profile}")
    adapter = Ts1201LearnAdapter()
    await adapter.async_start_learning(
        hass,
        resolved_ieee,
        timeout_s=timeout_s,
        endpoint_id=resolved_endpoint_id,
    )
    try:
        start = asyncio.get_running_loop().time()
        while True:
            try:
                payload = await adapter.async_read_learned_code(
                    hass,
                    resolved_ieee,
                    endpoint_id=resolved_endpoint_id,
                )
                payload[CONF_IEEE] = resolved_ieee
                payload["endpoint_id"] = resolved_endpoint_id
                payload[CONF_HUB_ID] = resolved_target.get(CONF_HUB_ID)
                return payload
            except ValueError:
                pass
            if asyncio.get_running_loop().time() - start >= timeout_s:
                raise TimeoutError("IR learn mode timeout")
            await asyncio.sleep(max(0.1, poll_interval_s))
    finally:
        await adapter.async_stop_learning(
            hass,
            resolved_ieee,
            endpoint_id=resolved_endpoint_id,
        )


async def learn_once_ts1201(
    hass: HomeAssistant,
    *,
    ieee: str,
    endpoint_id: int,
    timeout_s: float,
    poll_interval_s: float = 0.8,
) -> str:
    """Backward-compatible helper used by tests and callers expecting raw code string."""
    adapter = Ts1201LearnAdapter()
    await adapter.async_start_learning(
        hass,
        ieee,
        timeout_s=int(timeout_s),
        endpoint_id=endpoint_id,
    )
    try:
        start = asyncio.get_running_loop().time()
        while True:
            try:
                payload = await adapter.async_read_learned_code(
                    hass,
                    ieee,
                    endpoint_id=endpoint_id,
                )
                code = payload.get("code")
                if isinstance(code, str) and code:
                    return code
            except ValueError:
                pass
            if asyncio.get_running_loop().time() - start >= float(timeout_s):
                raise TimeoutError("IR learn mode timeout")
            await asyncio.sleep(max(0.1, poll_interval_s))
    finally:
        await adapter.async_stop_learning(
            hass,
            ieee,
            endpoint_id=endpoint_id,
        )
