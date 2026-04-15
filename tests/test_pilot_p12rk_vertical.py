"""End-to-end pilot slice: bundled LG P12RK (7062) capability flags + send + inbound attrs."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
EASYIR_PKG = ROOT / "custom_components" / "easyir"
sys.path.insert(0, str(EASYIR_PKG.parent))

import importlib

_easyir = importlib.import_module("custom_components.easyir")
# Allow relative imports inside climate.py (from .const ...).
sys.modules.setdefault("custom_components", importlib.import_module("custom_components"))
sys.modules.setdefault("custom_components.easyir", _easyir)

from custom_components.easyir.climate import EasyIrClimate  # noqa: E402
from custom_components.easyir.const import (  # noqa: E402
    CONF_ENDPOINT_ID,
    CONF_IEEE,
    CONF_PROFILE_PATH,
)

HELPERS_PATH = ROOT / "custom_components" / "easyir" / "helpers.py"
_SPEC = importlib.util.spec_from_file_location("easyir_helpers", HELPERS_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load helpers for tests")
_HELPERS = importlib.util.module_from_spec(_SPEC)
sys.modules["easyir_helpers"] = _HELPERS
_SPEC.loader.exec_module(_HELPERS)
clear_profile_cache = _HELPERS.clear_profile_cache
resolve_profile_raw = _HELPERS.resolve_profile_raw


PROFILE_7062 = ROOT / "custom_components" / "easyir" / "profiles" / "climate" / "7062.json"


class TestBundled7062CapabilitySend(unittest.TestCase):
    def setUp(self) -> None:
        clear_profile_cache()

    def tearDown(self) -> None:
        clear_profile_cache()

    def test_profile_declares_universal_extras(self) -> None:
        doc = json.loads(PROFILE_7062.read_text(encoding="utf-8"))
        flags = {str(x).strip().lower() for x in (doc.get("easyir_feature_flags") or [])}
        self.assertIn("ionizer", flags)
        self.assertIn("energy_saving", flags)
        self.assertIn("auto_clean", flags)

    def test_resolve_special_actions_via_universal_encoder(self) -> None:
        path = str(PROFILE_7062)
        ion_on = resolve_profile_raw(
            path=path,
            action="ionizer_on",
            hvac_mode="cool",
            fan_mode="auto",
            temperature=24,
        )
        ion_off = resolve_profile_raw(
            path=path,
            action="ionizer_off",
            hvac_mode="cool",
            fan_mode="auto",
            temperature=24,
        )
        self.assertEqual(len(ion_on), 59)
        self.assertEqual(len(ion_off), 59)
        self.assertNotEqual(ion_on, ion_off)

        es_on = resolve_profile_raw(
            path=path,
            action="energy_saving_on",
            hvac_mode="cool",
            fan_mode="auto",
            temperature=24,
        )
        es_off = resolve_profile_raw(
            path=path,
            action="energy_saving_off",
            hvac_mode="cool",
            fan_mode="auto",
            temperature=24,
        )
        self.assertNotEqual(es_on, es_off)


class TestClimateInboundFeatureFlags(unittest.TestCase):
    def test_inbound_updates_optional_feature_attributes(self) -> None:
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_IEEE: "aa:bb:cc:dd:ee:ff",
            CONF_PROFILE_PATH: str(PROFILE_7062),
            CONF_ENDPOINT_ID: 1,
        }
        from custom_components.easyir.protocols.lg_p12rk import climate_capability_view

        cap_view = climate_capability_view(str(PROFILE_7062))
        entity = EasyIrClimate(hass, entry, cap_view=cap_view)
        self.assertTrue(entity._cap_view.get("pilot"))
        self.assertTrue(entity._cap_view.get("ionizer_supported"))

        with patch.object(entity, "async_write_ha_state"):
            entity.async_handle_easyir_inbound_decoded(
                {"feature_flags": {"ionizer": True, "energy_saving": False}}
            )
        attrs = entity._attr_extra_state_attributes or {}
        self.assertTrue(attrs.get("easyir_ionizer_on"))
        self.assertFalse(attrs.get("easyir_energy_saving_on"))


if __name__ == "__main__":
    unittest.main()
