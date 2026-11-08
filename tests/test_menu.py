from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import restaurar as r
from test_restaurar import FakeAdb


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.adb = FakeAdb()
        self.profile = r.load_profile("menu")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "menu.json"

    def apply(self):
        before = r.snapshot(self.adb, self.profile)
        return r.apply_restore(self.adb, self.profile, before, self.path)

    def test_menu_mode_restores_home_but_keeps_other_optimizations(self):
        before_settings = deepcopy(self.adb.settings)
        after = self.apply()
        self.assertEqual({r.PACKAGES[0]: 0}, after["packages"])
        self.assertEqual({}, after["settings"])
        self.assertEqual(before_settings, self.adb.settings)
        self.assertEqual(3, self.adb.packages[r.PACKAGES[1]])
        self.assertEqual(3, self.adb.packages[r.PACKAGES[2]])
        self.assertFalse(any(call[0] == "settings" for call in self.adb.calls))
        self.assertTrue(all(call[-1] == r.PACKAGES[0] for call in self.adb.writes if call[0] == "pm"))

    def test_android14_menu_profile_is_exact_and_supported(self):
        self.adb.properties = deepcopy(self.profile["allowed_devices"][1])
        after = self.apply()
        self.assertEqual(r.canonical(r.STOCK_HOME), after["home"])
        self.assertEqual("complete", json.loads(self.path.read_text())["status"])

    def test_android14_rejects_full_android11_baseline(self):
        self.adb.properties = deepcopy(self.profile["allowed_devices"][1])
        with self.assertRaises(r.RestoreError):
            r.snapshot(self.adb, r.load_profile("base"))
        self.assertFalse(self.adb.writes)

    def test_unknown_firmware_is_still_rejected_in_menu_mode(self):
        self.adb.properties["fingerprint"] += "-unknown"
        with self.assertRaises(r.RestoreError):
            r.snapshot(self.adb, self.profile)
        self.assertFalse(self.adb.writes)

    def test_menu_mode_does_not_read_or_store_custom_dns(self):
        self.adb.settings["private_dns_specifier"] = "example.invalid"
        self.apply()
        self.assertNotIn("example.invalid", self.path.read_text())
        self.assertEqual("example.invalid", self.adb.settings["private_dns_specifier"])

    def test_menu_snapshot_cannot_be_used_for_full_baseline(self):
        before = r.snapshot(self.adb, self.profile)
        with self.assertRaises(r.RestoreError):
            r.make_plan(before, r.load_profile("base"))


if __name__ == "__main__":
    unittest.main()
