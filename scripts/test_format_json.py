#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "format_json.py"


def load_mod():
    spec = importlib.util.spec_from_file_location("format_json", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class FormatJsonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_mod()

    def test_collapses_short_primitive_arrays(self):
        text = self.mod.format_text(
            '{"tags":["plugin","text"],"verified_with":["0.114.1"]}'
        )
        self.assertIn('"tags": ["plugin", "text"]', text)
        self.assertIn('"verified_with": ["0.114.1"]', text)
        self.assertNotIn('"tags": [\n', text)

    def test_expands_long_primitive_arrays(self):
        targets = [
            "x86_64-unknown-linux-gnu",
            "aarch64-unknown-linux-gnu",
            "x86_64-apple-darwin",
            "aarch64-apple-darwin",
            "x86_64-pc-windows-msvc",
        ]
        payload = {"default_targets": targets}
        text = self.mod.format_text(
            __import__("json").dumps(payload),
            max_width=100,
        )
        self.assertIn('"default_targets": [\n', text)
        self.assertIn('"x86_64-unknown-linux-gnu"', text)

    def test_check_mode_detects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.json"
            path.write_text('{"tags":[ "a" ]}\n', encoding="utf-8")
            self.assertFalse(
                self.mod.format_path(path, check=True, max_width=100)
            )
            self.assertTrue(
                self.mod.format_path(path, check=False, max_width=100)
            )
            self.assertEqual(path.read_text(encoding="utf-8"), '{\n  "tags": ["a"]\n}\n')
            self.assertTrue(
                self.mod.format_path(path, check=True, max_width=100)
            )


if __name__ == "__main__":
    unittest.main()
