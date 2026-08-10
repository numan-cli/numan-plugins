#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_is_primitive_handles_bool_none_float(self):
        self.assertTrue(self.mod._is_primitive(True))
        self.assertTrue(self.mod._is_primitive(None))
        self.assertTrue(self.mod._is_primitive(1.5))
        self.assertFalse(self.mod._is_primitive([1]))
        self.assertFalse(self.mod._is_primitive({"a": 1}))

    def test_format_primitive_bool_null_float(self):
        self.assertEqual(self.mod._format_primitive(True), "true")
        self.assertEqual(self.mod._format_primitive(None), "null")
        self.assertEqual(self.mod._format_primitive(1.5), "1.5")

    def test_format_value_nested_dict_and_list(self):
        text = self.mod.format_text('{"a": {"b": [1, 2, {"c": true}]}}')
        self.assertIn('"a": {', text)
        self.assertIn('"b": [\n', text)
        self.assertIn('"c": true', text)

    def test_main_default_paths_check_mode(self):
        with mock.patch.object(sys, "argv", ["format_json.py", "--check"]):
            rc = self.mod.main()
        self.assertEqual(rc, 0)

    def test_main_missing_file_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            with mock.patch.object(sys, "argv", ["format_json.py", str(missing)]):
                rc = self.mod.main()
            self.assertEqual(rc, 2)

    def test_main_multi_file_dirty_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean.json"
            clean.write_text('{\n  "a": 1\n}\n', encoding="utf-8")
            dirty = root / "dirty.json"
            dirty.write_text('{"a":1}', encoding="utf-8")
            argv = ["format_json.py", "--check", str(clean), str(dirty)]
            with mock.patch.object(sys, "argv", argv):
                rc = self.mod.main()
            self.assertEqual(rc, 1)

    def test_main_success_prints_ok_and_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "sample.json"
            path.write_text('{"a":1}', encoding="utf-8")
            argv = ["format_json.py", str(path)]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(
                io.StringIO()
            ) as out:
                rc = self.mod.main()
            self.assertEqual(rc, 0)
            self.assertIn("OK: formatted 1 JSON file(s)", out.getvalue())

    def test_main_max_width_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "sample.json"
            path.write_text('{"tags":["a","b"]}', encoding="utf-8")
            argv = ["format_json.py", "--max-width", "5", str(path)]
            with mock.patch.object(sys, "argv", argv):
                rc = self.mod.main()
            self.assertEqual(rc, 0)
            self.assertIn('"tags": [\n', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
