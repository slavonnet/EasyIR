"""Config flow step handler coverage."""

from __future__ import annotations

import unittest

from custom_components.easyir.config_flow import (
    _climate_catalog_from_options,
    EasyIrConfigFlow,
    IrHubSubentryFlow,
    IrRemoteSubentryFlow,
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
        catalog = _climate_catalog_from_options(options)
        self.assertIn("LG", catalog)
        self.assertEqual(catalog["LG"][0]["value"], "climate/7062.json")
        self.assertEqual(catalog["LG"][0]["label"], "P12RK")
        self.assertIn("Midea", catalog)
        self.assertNotIn("Demo AC", catalog)


if __name__ == "__main__":
    unittest.main()
