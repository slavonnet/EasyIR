"""Config flow step handler coverage."""

from __future__ import annotations

import unittest

from custom_components.easyir.config_flow import (
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

    def test_hub_setup_step_exists(self) -> None:
        self.assertTrue(callable(getattr(EasyIrConfigFlow, "async_step_hub_setup", None)))

    def test_pick_hub_step_exists(self) -> None:
        self.assertTrue(callable(getattr(EasyIrConfigFlow, "async_step_pick_hub", None)))


if __name__ == "__main__":
    unittest.main()
