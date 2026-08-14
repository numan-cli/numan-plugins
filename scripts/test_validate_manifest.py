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

    def test_upstream_repo_requires_numan_maintained_owner(self):
        entry = self.entry(upstream_repo="original-author/plugin")
        with self.assertRaisesRegex(ValueError, "requires owner 'numan-maintained'"):
            self.mod.validate_manifest(self.manifest([entry]))

    def test_upstream_repo_accepted_with_numan_maintained_owner(self):
        entry = self.entry(owner="numan-maintained", upstream_repo="original-author/plugin")
        entries = self.mod.validate_manifest(self.manifest([entry]))
        self.assertEqual(entries[0]["upstream_repo"], "original-author/plugin")

    def test_rejects_blank_upstream_repo(self):
        entry = self.entry(owner="numan-maintained", upstream_repo="")
        with self.assertRaisesRegex(ValueError, "upstream_repo must be a non-empty string"):
            self.mod.validate_manifest(self.manifest([entry]))

    def test_numan_maintained_requires_upstream_repo(self):
        entry = self.entry(owner="numan-maintained")
        with self.assertRaisesRegex(ValueError, "requires upstream_repo"):
            self.mod.validate_manifest(self.manifest([entry]))

    def test_rejects_self_referential_upstream_repo(self):
        entry = self.entry(owner="numan-maintained", upstream_repo="Owner/Repo")
        with self.assertRaisesRegex(ValueError, "must not be the same as repo"):
            self.mod.validate_manifest(self.manifest([entry]))

    def test_rejects_malformed_upstream_repo(self):
        cases = [
            " https://github.com/original-author/plugin",
            "https://github.com/original-author/plugin",
            "original-author/",
            "/plugin",
            "original-author/plugin/extra",
        ]
        for upstream_repo in cases:
            with self.subTest(upstream_repo=upstream_repo):
                entry = self.entry(owner="numan-maintained", upstream_repo=upstream_repo)
                with self.assertRaisesRegex(ValueError, "owner/name"):
                    self.mod.validate_manifest(self.manifest([entry]))

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

    def test_selected_names_rejects_duplicates(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.mod.selected_names("a,a")

    def test_selected_names_returns_unique_list(self):
        self.assertEqual(self.mod.selected_names("a, b"), ["a", "b"])

    def test_expected_targets_rejects_invalid_defaults(self):
        manifest = {"default_targets": []}
        with self.assertRaisesRegex(ValueError, "non-empty unique list"):
            self.mod.expected_targets(manifest, self.entry())

    def test_expected_targets_rejects_duplicate_exclusions(self):
        manifest = self.manifest()
        entry = self.entry(exclude_targets=["linux", "linux"])
        with self.assertRaisesRegex(ValueError, "exclude_targets must be unique"):
            self.mod.expected_targets(manifest, entry)

    def test_expected_targets_rejects_unknown_exclusion(self):
        manifest = self.manifest()
        entry = self.entry(exclude_targets=["mac"])
        with self.assertRaisesRegex(ValueError, "unknown excluded targets"):
            self.mod.expected_targets(manifest, entry)

    def test_expected_targets_rejects_all_excluded(self):
        manifest = self.manifest()
        entry = self.entry(exclude_targets=["linux", "windows"])
        with self.assertRaisesRegex(ValueError, "all targets are excluded"):
            self.mod.expected_targets(manifest, entry)

    def test_validate_manifest_rejects_empty_active(self):
        with self.assertRaisesRegex(ValueError, "non-empty list"):
            self.mod.validate_manifest({"default_targets": ["linux"], "active": []})

    def test_validate_manifest_rejects_non_list_active(self):
        with self.assertRaisesRegex(ValueError, "non-empty list"):
            self.mod.validate_manifest({"default_targets": ["linux"], "active": "not-a-list"})

    def test_validate_manifest_rejects_non_dict_entry(self):
        manifest = {"default_targets": ["linux"], "active": ["not-a-dict"]}
        with self.assertRaisesRegex(ValueError, "must be objects"):
            self.mod.validate_manifest(manifest)

    def test_validate_manifest_rejects_missing_fields(self):
        entry = self.entry()
        del entry["description"]
        with self.assertRaisesRegex(ValueError, "missing fields"):
            self.mod.validate_manifest(self.manifest([entry]))

    def test_validate_manifest_rejects_empty_name(self):
        with self.assertRaisesRegex(ValueError, "name must be non-empty"):
            self.mod.validate_manifest(self.manifest([self.entry(name="")]))

    def test_resolve_tag_returns_sha_for_annotated_tag(self):
        with mock.patch.object(
            self.mod.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, "abc123 refs/tags/v1^{}\n", ""),
        ):
            self.assertEqual(self.mod.resolve_tag("owner/repo", "v1"), "abc123")

    def test_resolve_tag_raises_on_git_failure(self):
        with mock.patch.object(
            self.mod.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 1, "", "network error"),
        ):
            with self.assertRaisesRegex(ValueError, "failed to resolve"):
                self.mod.resolve_tag("owner/repo", "v1")

    def test_resolve_tag_raises_when_tag_missing(self):
        with mock.patch.object(
            self.mod.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ):
            with self.assertRaisesRegex(ValueError, "upstream tag not found"):
                self.mod.resolve_tag("owner/repo", "v1")

    def test_main_success_without_verify_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps(self.manifest()), encoding="utf-8")
            self.assertEqual(self.mod.main(["--manifest", str(manifest)]), 0)


if __name__ == "__main__":
    unittest.main()
