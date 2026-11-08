import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import restaurar as r


class FakeAdb:
    def __init__(self):
        self.profile = r.load_profile()
        self.properties = deepcopy(self.profile["device"])
        self.home = r.CUSTOM_HOME
        self.packages = dict.fromkeys(r.PACKAGES, 3)
        self.settings = dict(r.APPLIED)
        self.user = "0"
        self.device_state = "device"
        self.calls = []
        self.writes = []
        self.missing = None
        self.non_system = None
        self.hidden = None
        self.suspended = None
        self.drop_package_write = False
        self.drop_home_write = False
        self.drop_setting_write = False
        self.start_status = "ok"

    def run(self, *args):
        self.calls.append(args)
        if args == ("get-state",):
            return self.device_state
        raise AssertionError("Unexpected transport command: " + str(args))

    def shell(self, *args):
        self.calls.append(args)
        if args[0] == "getprop":
            names = {"ro.product.manufacturer": "manufacturer", "ro.product.model": "model",
                     "ro.product.device": "device", "ro.build.version.sdk": "sdk",
                     "ro.build.fingerprint": "fingerprint"}
            return self.properties[names[args[1]]]
        if args == ("am", "get-current-user"):
            return self.user
        if args[:3] == ("cmd", "package", "resolve-activity"):
            return "priority=2\n" + self.home
        if args[:2] == ("dumpsys", "package"):
            package = args[2]
            if package == self.missing:
                return "Unable to find package: " + package
            flags = "HAS_CODE" if package == self.non_system else "SYSTEM HAS_CODE"
            return ("Packages:\n  pkgFlags=[ " + flags + " ]\n"
                    "  User 0: installed=true hidden=" + str(package == self.hidden).lower()
                    + " suspended=" + str(package == self.suspended).lower()
                    + " enabled=" + str(self.packages[package]) + "\n")
        if args[:3] == ("settings", "get", "global"):
            value = self.settings[args[3]]
            return "null" if value is None else value
        self.writes.append(args)
        if args[:4] == ("pm", "default-state", "--user", "0"):
            if not self.drop_package_write:
                self.packages[args[4]] = 0
            return "new state: default"
        if args[:5] == ("cmd", "package", "set-home-activity", "--user", "0"):
            if not self.drop_home_write:
                self.home = args[5]
            return "Success"
        if args[:2] == ("am", "start"):
            return "Status: " + self.start_status + "\nActivity: " + self.home
        if args[:3] == ("settings", "delete", "global"):
            if not self.drop_setting_write:
                self.settings[args[3]] = None
            return "Deleted 1 rows"
        if args[:3] == ("settings", "put", "global"):
            if not self.drop_setting_write:
                self.settings[args[3]] = args[4]
            return ""
        raise AssertionError("Unexpected mutation: " + str(args))


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.adb = FakeAdb()
        self.profile = self.adb.profile
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state" / "restored.json"

    def capture(self):
        return r.snapshot(self.adb, self.profile)

    def apply(self):
        before = self.capture()
        return r.apply_restore(self.adb, self.profile, before, self.path)

    def test_original_animator_was_absent_not_one(self):
        self.assertIsNone(self.profile["settings"]["animator_duration_scale"])
        self.assertIsNone(self.profile["settings"]["private_dns_mode"])
        self.assertIsNone(self.profile["settings"]["private_dns_specifier"])

    def test_plan_only_reads(self):
        plan = r.make_plan(self.capture())
        self.assertEqual(list(r.PACKAGES), plan["packages"])
        self.assertEqual(list(r.ORIGINAL), plan["settings"])
        self.assertTrue(plan["home"])
        self.assertFalse(self.adb.writes)
        self.assertFalse(self.path.exists())

    def test_success_restores_exact_values_and_writes_journal(self):
        after = self.apply()
        self.assertEqual(r.ORIGINAL, after["settings"])
        self.assertEqual(dict.fromkeys(r.PACKAGES, 0), after["packages"])
        self.assertEqual(r.canonical(r.STOCK_HOME), after["home"])
        journal = json.loads(self.path.read_text())
        self.assertEqual("complete", journal["status"])
        self.assertTrue(all(item["verified"] for item in journal["events"]))
        self.assertEqual(dict(r.APPLIED), journal["before"]["settings"])
        self.assertNotIn("serial", journal)

    def test_home_is_confirmed_before_settings_are_changed(self):
        self.apply()
        opened = next(i for i, call in enumerate(self.adb.writes) if call[:2] == ("am", "start"))
        settings = next(i for i, call in enumerate(self.adb.writes) if call[0] == "settings")
        self.assertLess(opened, settings)
        self.assertEqual(("pm", "default-state", "--user", "0", r.PACKAGES[0]), self.adb.writes[0])

    def test_only_three_known_packages_and_five_settings_can_change(self):
        self.apply()
        self.assertEqual(set(r.PACKAGES), {c[-1] for c in self.adb.writes if c[0] == "pm"})
        self.assertEqual(set(r.ORIGINAL), {c[3] for c in self.adb.writes if c[0] == "settings"})
        self.assertFalse(any("uninstall" in c or "clear" in c or "reboot" in c for c in self.adb.calls))
        self.assertFalse(any("com.lite.fczx" in c or "org.smarttube.stable" in c for c in self.adb.calls))

    def test_mismatched_hardware_or_firmware_never_writes(self):
        for key in ("manufacturer", "model", "device", "sdk", "fingerprint"):
            with self.subTest(property=key):
                self.adb.properties = deepcopy(self.profile["device"])
                self.adb.properties[key] = "another-device"
                with self.assertRaises(r.RestoreError):
                    self.capture()
                self.assertFalse(self.adb.writes)

    def test_nonzero_user_never_writes(self):
        self.adb.user = "10"
        with self.assertRaises(r.RestoreError):
            self.capture()
        self.assertFalse(self.adb.writes)

    def test_offline_or_unauthorized_never_writes(self):
        for state in ("offline", "unauthorized", ""):
            self.adb.device_state = state
            with self.assertRaises(r.RestoreError):
                self.capture()
            self.assertFalse(self.adb.writes)

    def test_missing_system_package_never_writes(self):
        self.adb.missing = r.PACKAGES[0]
        with self.assertRaises(r.RestoreError):
            self.capture()
        self.assertFalse(self.adb.writes)

    def test_package_must_really_be_a_system_app(self):
        self.adb.non_system = r.PACKAGES[1]
        with self.assertRaises(r.RestoreError):
            self.capture()
        self.assertFalse(self.adb.writes)

    def test_hidden_or_suspended_package_is_not_overwritten(self):
        for key in ("hidden", "suspended"):
            self.adb = FakeAdb()
            setattr(self.adb, key, r.PACKAGES[1])
            with self.assertRaises(r.RestoreError):
                self.capture()
            self.assertFalse(self.adb.writes)

    def test_other_home_is_not_overwritten(self):
        self.adb.home = "com.example.other/.Home"
        with self.assertRaises(r.RestoreError):
            r.make_plan(self.capture())
        self.assertFalse(self.adb.writes)

    def test_other_dns_is_not_overwritten(self):
        self.adb.settings["private_dns_specifier"] = "example.invalid"
        with self.assertRaises(r.RestoreError):
            self.apply()
        self.assertFalse(self.adb.writes)
        self.assertFalse(self.path.exists())

    def test_other_animation_value_is_not_overwritten(self):
        self.adb.settings["animator_duration_scale"] = "0.0"
        with self.assertRaises(r.RestoreError):
            self.apply()
        self.assertFalse(self.adb.writes)

    def test_unexpected_package_disable_mode_is_rejected(self):
        for state in (2, 4):
            self.adb.packages[r.PACKAGES[1]] = state
            with self.assertRaises(r.RestoreError):
                self.apply()
            self.assertFalse(self.adb.writes)

    def test_manually_enabled_original_menu_can_return_to_default_state(self):
        self.adb.home = r.STOCK_HOME
        self.adb.packages[r.PACKAGES[0]] = 1
        self.assertEqual(0, self.apply()["packages"][r.PACKAGES[0]])

    def test_already_restored_state_is_idempotent(self):
        self.adb.home = r.STOCK_HOME
        self.adb.packages = dict.fromkeys(r.PACKAGES, 0)
        self.adb.settings = dict(r.ORIGINAL)
        plan = r.make_plan(self.capture())
        self.assertEqual({"packages": [], "home": False, "settings": []}, plan)
        self.apply()
        self.assertEqual(1, len(self.adb.writes))
        self.assertEqual(("am", "start"), self.adb.writes[0][:2])

    def test_state_change_during_confirmation_is_detected(self):
        before = self.capture()
        self.adb.home = r.STOCK_HOME
        with self.assertRaises(r.RestoreError):
            r.apply_restore(self.adb, self.profile, before, self.path)
        self.assertFalse(self.adb.writes)
        self.assertFalse(self.path.exists())

    def test_journal_creation_failure_never_changes_device(self):
        self.path.parent.mkdir()
        self.path.write_text("do not overwrite")
        with self.assertRaises(FileExistsError):
            self.apply()
        self.assertEqual("do not overwrite", self.path.read_text())
        self.assertFalse(self.adb.writes)

    def test_failed_package_write_stops_before_home_and_settings(self):
        self.adb.drop_package_write = True
        with self.assertRaises(r.RestoreError):
            self.apply()
        self.assertEqual(1, len(self.adb.writes))
        self.assertEqual("interrupted", json.loads(self.path.read_text())["status"])

    def test_failed_home_selection_stops_before_settings(self):
        self.adb.drop_home_write = True
        with self.assertRaises(r.RestoreError):
            self.apply()
        self.assertFalse(any(c[0] == "settings" for c in self.adb.writes))

    def test_timed_out_home_open_stops_before_settings(self):
        self.adb.start_status = "timeout"
        with self.assertRaises(r.RestoreError):
            self.apply()
        self.assertFalse(any(c[0] == "settings" for c in self.adb.writes))
        self.assertFalse(json.loads(self.path.read_text())["events"][-1]["verified"])

    def test_failed_setting_write_is_not_reported_as_success(self):
        self.adb.drop_setting_write = True
        with self.assertRaises(r.RestoreError):
            self.apply()
        journal = json.loads(self.path.read_text())
        self.assertEqual("interrupted", journal["status"])
        self.assertFalse(journal["events"][-1]["verified"])

    def test_fully_qualified_home_component_is_supported(self):
        self.adb.home = r.canonical(r.CUSTOM_HOME)
        self.assertTrue(r.make_plan(self.capture())["home"])

    def test_ambiguous_home_resolution_is_rejected(self):
        self.adb.home = r.CUSTOM_HOME + "\n" + r.STOCK_HOME
        with self.assertRaises(r.RestoreError):
            self.capture()

    def test_cli_defaults_to_read_only(self):
        with patch.object(r, "Adb", return_value=self.adb), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(0, r.main(["--serial", "SYNTHETIC-DEVICE"]))
        self.assertIn("Solo lectura", out.getvalue())
        self.assertFalse(self.adb.writes)

    def test_noninteractive_apply_requires_explicit_confirmation(self):
        with patch.object(r, "Adb", return_value=self.adb), patch.object(r.sys.stdin, "isatty", return_value=False):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(1, r.main(["--serial", "SYNTHETIC-DEVICE", "--apply"]))
        self.assertFalse(self.adb.writes)

    def test_interactive_cancel_does_not_mutate(self):
        with patch.object(r, "Adb", return_value=self.adb), patch.object(r.sys.stdin, "isatty", return_value=True):
            with patch("builtins.input", return_value="NO"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, r.main(["--serial", "SYNTHETIC-DEVICE", "--apply"]))
        self.assertFalse(self.adb.writes)


class TransportTests(unittest.TestCase):
    def test_adb_always_targets_one_explicit_device(self):
        commands = []

        def runner(args, **kwargs):
            commands.append(args)
            self.assertFalse(kwargs.get("shell", False))
            self.assertEqual(45, kwargs["timeout"])
            return subprocess.CompletedProcess(args, 0, "device\n", "")

        self.assertEqual("device", r.Adb("adb", "SYNTHETIC-DEVICE", runner=runner).run("get-state"))
        self.assertEqual(["adb", "-P", "5038", "-s", "SYNTHETIC-DEVICE", "get-state"], commands[0])

    def test_invalid_serial_or_port_is_rejected(self):
        for serial in ("", "name with spaces", "a;command", "a\ncommand"):
            with self.assertRaises(r.RestoreError):
                r.Adb("adb", serial)
        for port in (0, 65536):
            with self.assertRaises(r.RestoreError):
                r.Adb("adb", "SYNTHETIC-DEVICE", port=port)

    def test_reported_shell_error_even_with_zero_exit_is_rejected(self):
        for output in ("Error: no permission", "Failure [blocked]", "Exception occurred while executing"):
            def runner(args, **kwargs):
                return subprocess.CompletedProcess(args, 0, output, "")
            with self.assertRaises(r.RestoreError):
                r.Adb("adb", "SYNTHETIC-DEVICE", runner=runner).shell("cmd", "package")

    def test_transport_timeout_is_bounded(self):
        def runner(args, **kwargs):
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        with self.assertRaises(r.RestoreError):
            r.Adb("adb", "SYNTHETIC-DEVICE", runner=runner).run("get-state")

    def test_missing_adb_is_reported_without_changes(self):
        def runner(args, **kwargs):
            raise FileNotFoundError("adb")
        with self.assertRaises(r.RestoreError):
            r.Adb("adb", "SYNTHETIC-DEVICE", runner=runner).run("get-state")


if __name__ == "__main__":
    unittest.main()
