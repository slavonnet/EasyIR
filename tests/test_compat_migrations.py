"""Config entry migration and upgrade regression for EasyIR."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import SOURCE_USER, ConfigEntry, ConfigEntryState
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant

REPO_ROOT = Path(__file__).resolve().parent.parent
DOMAIN = "easyir"
HELPERS_PATH = REPO_ROOT / "custom_components" / "easyir" / "helpers.py"
_SPEC = importlib.util.spec_from_file_location("easyir_helpers", HELPERS_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load helpers module for tests")
_HELPERS = importlib.util.module_from_spec(_SPEC)
sys.modules["easyir_helpers"] = _HELPERS
_SPEC.loader.exec_module(_HELPERS)

clear_profile_cache = _HELPERS.clear_profile_cache
encode_raw_to_tuya_base64 = _HELPERS.encode_raw_to_tuya_base64
resolve_profile_raw = _HELPERS.resolve_profile_raw

# Register config flow handler (ConfigFlow.__init_subclass__).
import custom_components.easyir.config_flow  # noqa: F401
import custom_components.easyir as easyir_pkg


def _demo_profile_path() -> str:
    return str(REPO_ROOT / "custom_components" / "easyir" / "profiles" / "demo_ac.json")


def _make_entry(
    *,
    version: int,
    data: dict[str, object],
    minor_version: int = 1,
) -> ConfigEntry:
    return ConfigEntry(
        version=version,
        minor_version=minor_version,
        domain=DOMAIN,
        title="EasyIR",
        data=data,
        source=SOURCE_USER,
        options={},
        discovery_keys=MappingProxyType({}),
        unique_id="testunique",
        state=ConfigEntryState.NOT_LOADED,
    )


class TestAsyncMigrateEntry(unittest.IsolatedAsyncioTestCase):
    """Exercise ``async_migrate_entry`` with a minimal Home Assistant core."""

    async def asyncSetUp(self) -> None:
        self.hass = HomeAssistant("/tmp/easyir_migration_test")
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self._integration = MagicMock()
        self._integration.domain = DOMAIN
        self._integration.async_get_component = AsyncMock(return_value=easyir_pkg)

    async def asyncTearDown(self) -> None:
        await self.hass.async_stop(force=True)

    async def test_migrate_v1_preserves_data_when_complete(self) -> None:
        path = _demo_profile_path()
        data = {"ieee": "aa:bb:cc:dd:ee:ff", "profile_path": path, "endpoint_id": 2}
        entry = _make_entry(version=1, data=data.copy())
        object.__setattr__(entry, "_integration_for_domain", self._integration)
        self.hass.config_entries._entries[entry.entry_id] = entry  # noqa: SLF001

        ok = await easyir_pkg.async_migrate_entry(self.hass, entry)
        self.assertTrue(ok)
        self.assertEqual(entry.version, 2)
        self.assertEqual(dict(entry.data), data)

    async def test_migrate_v1_adds_missing_endpoint_id(self) -> None:
        path = _demo_profile_path()
        entry = _make_entry(
            version=1,
            data={"ieee": "aa:bb:cc:dd:ee:ff", "profile_path": path},
        )
        object.__setattr__(entry, "_integration_for_domain", self._integration)
        self.hass.config_entries._entries[entry.entry_id] = entry  # noqa: SLF001

        ok = await easyir_pkg.async_migrate_entry(self.hass, entry)
        self.assertTrue(ok)
        self.assertEqual(entry.version, 2)
        self.assertEqual(
            dict(entry.data),
            {"ieee": "aa:bb:cc:dd:ee:ff", "profile_path": path, "endpoint_id": 1},
        )

    async def test_migrate_rejects_unknown_future_entry_version(self) -> None:
        entry = _make_entry(
            version=99,
            data={"ieee": "x", "profile_path": _demo_profile_path(), "endpoint_id": 1},
        )
        object.__setattr__(entry, "_integration_for_domain", self._integration)

        ok = await easyir_pkg.async_migrate_entry(self.hass, entry)
        self.assertFalse(ok)

    async def test_config_entry_async_migrate_calls_integration_handler(self) -> None:
        """Matches Home Assistant ``ConfigEntry.async_migrate`` wiring."""
        path = _demo_profile_path()
        entry = _make_entry(
            version=1,
            data={"ieee": "aa:bb:cc:dd:ee:ff", "profile_path": path},
        )
        object.__setattr__(entry, "_integration_for_domain", self._integration)
        self.hass.config_entries._entries[entry.entry_id] = entry  # noqa: SLF001

        ok = await entry.async_migrate(self.hass)
        self.assertTrue(ok)
        self.assertEqual(entry.version, 2)
        self.assertEqual(dict(entry.data)["endpoint_id"], 1)


class TestMigratedEntryProfileSendRegression(unittest.TestCase):
    """After migration shape, profile resolution + TS1201 encoding stay stable."""

    _EXPECTED_OFF = "BegD0Af0AQ=="

    def setUp(self) -> None:
        clear_profile_cache()

    def tearDown(self) -> None:
        clear_profile_cache()

    def test_post_migration_data_resolves_off_like_baseline(self) -> None:
        path = _demo_profile_path()
        migrated = {"ieee": "aa:bb:cc:dd:ee:ff", "profile_path": path, "endpoint_id": 1}
        self.assertEqual(
            set(migrated.keys()),
            {"ieee", "profile_path", "endpoint_id"},
        )
        raw = resolve_profile_raw(path=migrated["profile_path"], action="off")
        self.assertEqual(encode_raw_to_tuya_base64(raw), self._EXPECTED_OFF)

    def test_fixture_minimal_ac_still_valid_json(self) -> None:
        p = REPO_ROOT / "tests" / "fixtures" / "legacy_config_entries" / "minimal_ac.json"
        payload = json.loads(p.read_text(encoding="utf-8"))
        self.assertIn("commands", payload)
