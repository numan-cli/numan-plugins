#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from unittest import mock
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "validate_manifest.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_manifest", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ValidateManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def entry(self, **changes):
        result = {
            "repo": "owner/repo",
            "name": "plugin",
            "owner": "owner",
            "plugin_bin": "plugin",
            "tag": "v1",
            "source_commit": "a" * 40,
            "version": "1.0.0",
            "nu_version": "*",
            "verified_with": ["0.114.1"],
            "description": "plugin",
            "tags": ["plugin"],
        }
        result.update(changes)
        return result

    def manifest(self, entries=None):
        return {"default_targets": ["linux", "windows"], "active": entries or [self.entry()]}

    def test_validates_selected_entry_and_targets(self):
        entries = self.mod.validate_manifest(self.manifest(), ["plugin"])
        self.assertEqual([entry["name"] for entry in entries], ["plugin"])
        self.assertEqual(self.mod.expected_targets(self.manifest(), entries[0]), ["linux", "windows"])

    def test_rejects_blank_selection(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            self.mod.selected_names(" , ")

    def test_rejects_duplicate_names(self):
        with self.assertRaisesRegex(ValueError, "duplicate active"):
            self.mod.validate_manifest(self.manifest([self.entry(), self.entry()]))

    def test_rejects_invalid_commit(self):
        with self.assertRaisesRegex(ValueError, "40 lowercase"):
            self.mod.validate_manifest(self.manifest([self.entry(source_commit="ABC")]))

    def test_rejects_unknown_selection(self):
        with self.assertRaisesRegex(ValueError, "unknown active"):
            self.mod.validate_manifest(self.manifest(), ["missing"])

    def test_verifies_tag_mapping(self):
        with mock.patch.object(self.mod, "resolve_tag", return_value="a" * 40):
            self.mod.verify_upstream([self.entry()])
        with mock.patch.object(self.mod, "resolve_tag", return_value="b" * 40):
            with self.assertRaisesRegex(ValueError, "resolves to"):
                self.mod.verify_upstream([self.entry()])


if __name__ == "__main__":
    unittest.main()
