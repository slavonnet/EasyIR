"""IR learn-mode control and payload readback per hub profile."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .command_pool import async_call_pooled_service
from .const import (
    CONF_IEEE,
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


def _entry_endpoint_id(entry_data: dict[str, Any] | None) -> int:
    if not entry_data:
        return DEFAULT_ENDPOINT_ID
    try:
        return int(entry_data.get("endpoint_id", DEFAULT_ENDPOINT_ID))
    except (TypeError, ValueError):
        return DEFAULT_ENDPOINT_ID


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


async def _read_last_learned(hass: HomeAssistant, ieee: str, endpoint_id: int) -> str | None:
    result = await async_call_pooled_service(
        hass,
        ieee=ieee,
        domain=ZHA_DOMAIN,
        service="read_zigbee_cluster_attributes",
        data={
            "ieee": ieee,
            "endpoint_id": endpoint_id,
            "cluster_id": TS1201_CLUSTER_ID,
            "cluster_type": TS1201_CLUSTER_TYPE,
            "attribute": [TS1201_LAST_LEARNED_ATTR_ID],
        },
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
    timeout_s: int = 30,
) -> dict[str, Any]:
    """Start learn mode for one hub according to vendor profile implementation."""
    if vendor_profile != VENDOR_PROFILE_TS1201_ZOSUNG:
        raise ValueError(f"Unsupported learn vendor profile: {vendor_profile}")
    entry_data = _entry_for_ieee(hass, ieee)
    adapter = Ts1201LearnAdapter()
    return await adapter.async_start_learning(
        hass,
        ieee,
        timeout_s=timeout_s,
        endpoint_id=_entry_endpoint_id(entry_data),
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
    ieee: str,
    endpoint_id: int,
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
    vendor_profile = await async_detect_ir_learn_profile(hass, ieee)
    if vendor_profile != VENDOR_PROFILE_TS1201_ZOSUNG:
        raise ValueError("No supported learn profile for this IR hub")
    adapter = Ts1201LearnAdapter()
    await adapter.async_start_learning(
        hass,
        ieee,
        timeout_s=timeout_s,
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
                return payload
            except ValueError:
                pass
            if asyncio.get_running_loop().time() - start >= timeout_s:
                raise TimeoutError("IR learn mode timeout")
            await asyncio.sleep(max(0.1, poll_interval_s))
    finally:
        await adapter.async_stop_learning(
            hass,
            ieee,
            endpoint_id=endpoint_id,
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
