#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "ensure_release_absent.py"


def load_module():
    """
    Load and return the release-checking module from its script path.
    
    Returns:
        module: The dynamically loaded module.
    """
    spec = importlib.util.spec_from_file_location("ensure_release_absent", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class EnsureReleaseAbsentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    @staticmethod
    def result(code, stdout="", stderr=""):
        return subprocess.CompletedProcess([], code, stdout, stderr)

    def test_accepts_confirmed_not_found(self):
        self.mod.ensure_absent("o/r", "p-1", lambda *args, **kwargs: self.result(1, stderr="404 Not Found"))

    def test_rejects_existing_release(self):
        results = iter(
            [
                self.result(1, stderr="404 Not Found"),
                self.result(0),
            ]
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.mod.ensure_absent("o/r", "p-1", lambda *args, **kwargs: next(results))

    def test_rejects_existing_tag_before_checking_release(self):
        with self.assertRaisesRegex(ValueError, "tag .* already exists"):
            self.mod.ensure_absent("o/r", "p-1", lambda *args, **kwargs: self.result(0))

    def test_fails_closed_on_api_error(self):
        with self.assertRaisesRegex(RuntimeError, "could not prove"):
            self.mod.ensure_absent("o/r", "p-1", lambda *args, **kwargs: self.result(1, stderr="rate limited"))

    def test_timeout_fails_cleanly(self):
        """Return a normal failure code when GitHub does not respond in time."""
        with mock.patch.object(
            self.mod,
            "ensure_absent",
            side_effect=subprocess.TimeoutExpired(["gh"], 30),
        ):
            self.assertEqual(1, self.mod.main(["--repo", "o/r", "--tag", "p-1"]))


if __name__ == "__main__":
    unittest.main()
