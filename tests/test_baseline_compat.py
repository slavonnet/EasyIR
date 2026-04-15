"""Regression tests for MVP compatibility baseline (config + profile resolution).

These tests do not import Home Assistant; they lock helpers/constants behavior
that existing config entries rely on for sending commands.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "legacy_config_entries"
CONST_PATH = REPO_ROOT / "custom_components" / "easyir" / "const.py"
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


def _expand_repo_root(value: str) -> str:
    return value.replace("${EASYIR_REPO_ROOT}", str(REPO_ROOT))


def _load_entry_fixtures() -> list[tuple[str, dict[str, object]]]:
    out: list[tuple[str, dict[str, object]]] = []
    for path in sorted(FIXTURE_DIR.glob("*.entry.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        data = payload["data"]
        if not isinstance(data, dict):
            raise AssertionError(f"{path.name}: 'data' must be an object")
        expanded = {
            k: _expand_repo_root(v) if isinstance(v, str) else v
            for k, v in data.items()
        }
        out.append((path.stem, expanded))
    return out


class TestBaselineConstants(unittest.TestCase):
    def test_service_and_config_keys_match_runtime_module(self) -> None:
        """const.py keys must stay aligned with documented baseline."""
        ns: dict[str, object] = {}
        exec(CONST_PATH.read_text(encoding="utf-8"), ns)
        self.assertEqual(ns["DOMAIN"], "easyir")
        self.assertEqual(ns["SERVICE_SEND_RAW"], "send_raw")
        self.assertEqual(ns["SERVICE_SEND_COMMAND"], "send_profile_command")
        self.assertEqual(ns["CONF_IEEE"], "ieee")
        self.assertEqual(ns["CONF_PROFILE_PATH"], "profile_path")
        self.assertEqual(ns["CONF_ENDPOINT_ID"], "endpoint_id")
        self.assertEqual(ns["DEFAULT_ENDPOINT_ID"], 1)


class TestLegacyConfigEntryRegression(unittest.TestCase):
    """Golden paths for shapes stored in real HA config entries."""

    _EXPECTED_OFF_BASE64 = {
        "bundled_demo_ac_registry_id.entry": "BegD0Af0AQ==",
        "bundled_climate_7062.entry": (
            "H8QiNhD0ASwG9AEmAvQBJgL0ASYC9AEsBvQBJgL0ASYCH/QBJgL0ASwG9AEsBvQBJgL0ASYC9AEm"
            "AvQBJgL0ASYCH/QBJgL0ASYC9AEmAvQBJgL0ASYC9AEmAvQBLAb0ASYCFfQBLAb0ASYC9AEmAvQBJgL0"
            "ASwG//8="
        ),
        "custom_absolute_path.entry": "BegD0Af0AQ==",
    }

    def setUp(self) -> None:
        clear_profile_cache()

    def tearDown(self) -> None:
        clear_profile_cache()

    def test_entry_fixture_files_present(self) -> None:
        fixtures = _load_entry_fixtures()
        self.assertGreaterEqual(len(fixtures), 3, msg="expected >=3 *.entry.json fixtures")

    def test_legacy_entry_required_keys_and_types(self) -> None:
        for name, data in _load_entry_fixtures():
            with self.subTest(fixture=name):
                self.assertEqual(
                    set(data.keys()),
                    {"ieee", "profile_path", "endpoint_id"},
                    msg=f"{name}: legacy entry data keys must not drift",
                )
                self.assertIsInstance(data["ieee"], str)
                self.assertIsInstance(data["profile_path"], str)
                self.assertIsInstance(data["endpoint_id"], int)

    def test_legacy_profile_paths_resolve_off_timings(self) -> None:
        for name, data in _load_entry_fixtures():
            with self.subTest(fixture=name):
                path = str(data["profile_path"])
                raw = resolve_profile_raw(path=path, action="off")
                self.assertIsInstance(raw, list)
                self.assertGreater(len(raw), 0)

    def test_legacy_send_profile_off_encoding_stable(self) -> None:
        for name, data in _load_entry_fixtures():
            with self.subTest(fixture=name):
                expected = self._EXPECTED_OFF_BASE64.get(name)
                self.assertIsNotNone(
                    expected,
                    msg=f"add golden base64 for new fixture {name!r}",
                )
                path = str(data["profile_path"])
                raw = resolve_profile_raw(path=path, action="off")
                self.assertEqual(encode_raw_to_tuya_base64(raw), expected)

    def test_bundled_contract_paths_exist(self) -> None:
        """Shipped paths referenced by users and docs must remain present."""
        profiles = REPO_ROOT / "custom_components" / "easyir" / "profiles"
        self.assertTrue((profiles / "registry.json").is_file())
        self.assertTrue((profiles / "demo_ac.json").is_file())
        self.assertTrue((profiles / "climate" / "7062.json").is_file())
        self.assertTrue((profiles / "climate_index.json").is_file())
