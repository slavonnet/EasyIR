"""Config flow step handler coverage."""

from __future__ import annotations

import unittest

from custom_components.easyir.config_flow import EasyIrConfigFlow


class TestConfigFlowSteps(unittest.TestCase):
    def test_manage_step_handler_exists(self) -> None:
        self.assertTrue(callable(getattr(EasyIrConfigFlow, "async_step_manage", None)))

    def test_hub_remote_step_handler_exists(self) -> None:
        self.assertTrue(callable(getattr(EasyIrConfigFlow, "async_step_hub_remote", None)))


if __name__ == "__main__":
    unittest.main()
