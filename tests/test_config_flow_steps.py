"""Config flow step handler coverage."""

from __future__ import annotations

import unittest

from custom_components.easyir.config_flow import EasyIrConfigFlow


class TestConfigFlowSteps(unittest.TestCase):
    def test_main_menu_step_handler_exists(self) -> None:
        self.assertTrue(callable(getattr(EasyIrConfigFlow, "async_step_main_menu", None)))

    def test_add_hub_step_handler_exists(self) -> None:
        self.assertTrue(callable(getattr(EasyIrConfigFlow, "async_step_add_hub", None)))

    def test_hub_remote_step_handler_exists(self) -> None:
        self.assertTrue(callable(getattr(EasyIrConfigFlow, "async_step_hub_remote", None)))

    def test_pick_hub_step_handler_exists(self) -> None:
        self.assertTrue(callable(getattr(EasyIrConfigFlow, "async_step_pick_hub", None)))


if __name__ == "__main__":
    unittest.main()
