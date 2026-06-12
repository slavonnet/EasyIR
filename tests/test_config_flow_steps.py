"""Config flow step handler coverage."""

from __future__ import annotations

import unittest
from types import MappingProxyType, SimpleNamespace

from custom_components.easyir.config_flow import (
    EasyIrConfigFlow,
    IrHubSubentryFlow,
    IrRemoteSubentryFlow,
)
from custom_components.easyir.const import SUBENTRY_TYPE_REMOTE
from custom_components.easyir.remote_catalog import (
    climate_catalog_from_options,
    non_climate_catalog_from_options,
    tv_catalog_from_options,
)


class TestConfigFlowSteps(unittest.TestCase):
    def test_parent_flow_version_is_v4(self) -> None:
        self.assertEqual(EasyIrConfigFlow.VERSION, 4)

    def test_subentry_types_registered(self) -> None:
        types = EasyIrConfigFlow.async_get_supported_subentry_types(None)
        self.assertIn("ir_hub", types)
        self.assertIn("ir_remote", types)
        self.assertIs(types["ir_hub"], IrHubSubentryFlow)
        self.assertIs(types["ir_remote"], IrRemoteSubentryFlow)

    def test_combined_user_step_exists(self) -> None:
        self.assertTrue(callable(getattr(EasyIrConfigFlow, "async_step_user", None)))

    def test_manual_hub_step_exists(self) -> None:
        self.assertTrue(callable(getattr(EasyIrConfigFlow, "async_step_hub_manual", None)))

    def test_remote_subentry_has_expected_steps(self) -> None:
        self.assertTrue(callable(getattr(IrRemoteSubentryFlow, "async_step_user", None)))
        self.assertTrue(
            callable(getattr(IrRemoteSubentryFlow, "async_step_remote_type", None))
        )
        self.assertTrue(
            callable(getattr(IrRemoteSubentryFlow, "async_step_remote_brand", None))
        )
        self.assertTrue(
            callable(getattr(IrRemoteSubentryFlow, "async_step_hub_remote", None))
        )

    def test_climate_catalog_groups_brand_and_model(self) -> None:
        options = [
            {"value": "climate/7062.json", "label": "LG — P12RK"},
            {"value": "climate/7386.json", "label": "Midea — KFR-32GW"},
            {"value": "demo_ac", "label": "Demo AC"},
        ]
        catalog = climate_catalog_from_options(options)
        self.assertIn("LG", catalog)
        self.assertEqual(catalog["LG"][0]["value"], "climate/7062.json")
        self.assertEqual(catalog["LG"][0]["label"], "P12RK")
        self.assertIn("Midea", catalog)
        self.assertNotIn("Demo AC", catalog)

    def test_tv_catalog_filters_non_climate_by_name(self) -> None:
        options = [
            {"value": "climate/7062.json", "label": "LG — P12RK"},
            {"value": "tv/samsung_q80.json", "label": "Samsung TV — Q80"},
            {"value": "demo_ac", "label": "Demo AC"},
        ]
        catalog = tv_catalog_from_options(options)
        self.assertIn("Samsung TV", catalog)
        self.assertEqual(catalog["Samsung TV"][0]["value"], "tv/samsung_q80.json")
        self.assertNotIn("LG", catalog)

    def test_non_climate_catalog_omits_climate_profiles(self) -> None:
        options = [
            {"value": "climate/7062.json", "label": "LG — P12RK"},
            {"value": "demo_ac", "label": "Demo AC"},
        ]
        catalog = non_climate_catalog_from_options(options)
        self.assertNotIn("LG", catalog)
        self.assertIn("Other", catalog)

    def test_next_remote_unique_id_adds_suffix_when_duplicate_exists(self) -> None:
        flow = IrRemoteSubentryFlow()
        parent = SimpleNamespace(
            subentries=MappingProxyType(
                {
                    "r1": SimpleNamespace(
                        subentry_type=SUBENTRY_TYPE_REMOTE, unique_id="hub1_7062"
                    ),
                    "r2": SimpleNamespace(
                        subentry_type=SUBENTRY_TYPE_REMOTE, unique_id="hub1_7062_2"
                    ),
                }
            )
        )
        flow._get_entry = lambda: parent  # type: ignore[method-assign]
        unique = flow._next_remote_unique_id(  # type: ignore[attr-defined]
            hub_id="hub1", profile_path="/tmp/7062.json"
        )
        self.assertEqual(unique, "hub1_7062_3")


if __name__ == "__main__":
    unittest.main()
