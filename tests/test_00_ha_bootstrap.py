"""Install HA config subentry stubs before other tests import easyir."""

from __future__ import annotations

import unittest

from tests.ha_subentry_stubs import install

install()


class TestHaSubentryBootstrap(unittest.TestCase):
    def test_subentry_api_available(self) -> None:
        from homeassistant.config_entries import ConfigSubentryFlow

        self.assertTrue(ConfigSubentryFlow is not None)


if __name__ == "__main__":
    unittest.main()
