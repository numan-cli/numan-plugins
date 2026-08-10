#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent / "validate_manifest.py"


def load_module():
    """
    Load and return the manifest validation module from its script path.
    
    Returns:
        module: The dynamically loaded `validate_manifest` module.
    """
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
        """
        Create a baseline manifest entry with optional field overrides.
        
        Parameters:
        	**changes (dict): Manifest fields to add or replace in the baseline entry.
        
        Returns:
        	dict: A manifest entry dictionary.
        """
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
        """
        Create a manifest with default targets and active entries.
        
        Parameters:
        	entries (list, optional): Manifest entries to include as active entries.
        
        Returns:
        	dict: A manifest containing the default targets and active entries.
        """
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

    def test_upstream_timeout_fails_cleanly(self):
        """Return a normal validation failure when an upstream lookup times out."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps(self.manifest()), encoding="utf-8")
            with mock.patch.object(
                self.mod.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(["git"], 30),
            ):
                self.assertEqual(
                    1,
                    self.mod.main(["--manifest", str(manifest), "--verify-upstream"]),
                )

    def test_commit_snapshot_entry_allows_null_tag(self):
        entries = self.mod.validate_manifest(
            self.manifest([self.entry(intake_mode="commit-snapshot", tag=None)])
        )
        self.assertEqual([entry["name"] for entry in entries], ["plugin"])

    def test_commit_snapshot_entry_allows_absent_tag_key(self):
        entry = self.entry(intake_mode="commit-snapshot")
        del entry["tag"]
        entries = self.mod.validate_manifest(self.manifest([entry]))
        self.assertEqual([entry["name"] for entry in entries], ["plugin"])

    def test_tagged_entry_still_requires_tag(self):
        entry = self.entry(tag=None)
        with self.assertRaisesRegex(ValueError, "tag is required"):
            self.mod.validate_manifest(self.manifest([entry]))

    def test_rejects_unknown_intake_mode(self):
        with self.assertRaisesRegex(ValueError, "intake_mode must be one of"):
            self.mod.validate_manifest(self.manifest([self.entry(intake_mode="bogus")]))

    def test_verify_upstream_skips_tag_check_for_commit_snapshot(self):
        entry = self.entry(intake_mode="commit-snapshot")
        with mock.patch.object(self.mod, "resolve_tag") as resolve_tag:
            with mock.patch.object(self.mod, "verify_commit_exists"):
                self.mod.verify_upstream([entry])
                resolve_tag.assert_not_called()

    def test_verify_upstream_checks_commit_exists_for_commit_snapshot(self):
        entry = self.entry(intake_mode="commit-snapshot")
        with mock.patch.object(self.mod, "verify_commit_exists") as verify_commit_exists:
            self.mod.verify_upstream([entry])
            verify_commit_exists.assert_called_once_with(entry["repo"], entry["source_commit"])

    def test_verify_upstream_fails_when_snapshot_commit_missing_upstream(self):
        entry = self.entry(intake_mode="commit-snapshot")
        with mock.patch.object(
            self.mod,
            "verify_commit_exists",
            side_effect=ValueError("source_commit not found upstream: owner/repo@" + "a" * 40),
        ):
            with self.assertRaisesRegex(ValueError, "source_commit not found upstream"):
                self.mod.verify_upstream([entry])

    def test_rejects_non_string_intake_mode_list(self):
        with self.assertRaisesRegex(ValueError, "intake_mode must be one of"):
            self.mod.validate_manifest(self.manifest([self.entry(intake_mode=["tagged"])]))

    def test_rejects_non_string_intake_mode_dict(self):
        with self.assertRaisesRegex(ValueError, "intake_mode must be one of"):
            self.mod.validate_manifest(self.manifest([self.entry(intake_mode={"mode": "tagged"})]))

    def test_rejects_null_source_commit(self):
        with self.assertRaisesRegex(ValueError, "source_commit must be 40 lowercase"):
            self.mod.validate_manifest(self.manifest([self.entry(source_commit=None)]))

    def test_rejects_non_string_source_commit(self):
        with self.assertRaisesRegex(ValueError, "source_commit must be 40 lowercase"):
            self.mod.validate_manifest(self.manifest([self.entry(source_commit=123)]))

    def test_verify_upstream_rejects_non_commit_object(self):
        entry = self.entry(intake_mode="commit-snapshot")
        with mock.patch.object(
            self.mod,
            "verify_commit_exists",
            side_effect=ValueError("source_commit is not a commit object: owner/repo@" + "a" * 40),
        ):
            with self.assertRaisesRegex(ValueError, "source_commit is not a commit object"):
                self.mod.verify_upstream([entry])


if __name__ == "__main__":
    unittest.main()
