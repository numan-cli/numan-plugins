#!/usr/bin/env python3
"""Unit tests for scripts/bump_manifest_from_upstream.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bump_manifest_from_upstream as bmu  # noqa: E402


class BumpManifestFromUpstreamTests(unittest.TestCase):
    def _sample_entry(self) -> dict:
        return {
            "repo": " example/nu_plugin_demo ",
            "name": "nu_plugin_demo",
            "owner": "example",
            "intake_mode": "tagged",
            "tag": "v0.2.0",
            "source_commit": "a" * 40,
            "version": "0.2.0",
            "nu_version": ">=0.111.0 <0.112.0",
            "verified_with": ["0.111.0"],
            "plugin_bin": "nu_plugin_demo",
            "description": "Demo plugin",
            "tags": ["plugin"],
        }

    def _run_bump_with_mocked_upstream(
        self,
        entry: dict,
        tag_name: str,
        sha: str,
        cargo_nu: str | None,
    ) -> tuple[bool, str, dict | None]:
        with (
            mock.patch.object(bmu, "_check_tag_moved", return_value=False),
            mock.patch.object(
                bmu,
                "fetch_latest_tags",
                return_value=[{"name": tag_name, "commit_sha": sha}],
            ),
            mock.patch.object(bmu, "resolve_tag_commit", return_value=sha),
            mock.patch.object(bmu, "fetch_cargo_toml_nu_dep", return_value=cargo_nu),
        ):
            return bmu.bump_entry(entry)

    def test_bumps_minor_tag_and_updates_nu_version(self):
        entry = self._sample_entry()
        new_sha = "B" * 40
        with (
            mock.patch.object(bmu, "_check_tag_moved", return_value=False) as m_moved,
            mock.patch.object(
                bmu,
                "fetch_latest_tags",
                return_value=[
                    {"name": "v0.4.0-rc.1", "commit_sha": "f" * 40},
                    {"name": "v0.2.1", "commit_sha": "e" * 40},
                    {"name": "v0.3.0", "commit_sha": new_sha},
                ],
            ) as m_tags,
            mock.patch.object(bmu, "resolve_tag_commit", return_value=new_sha),
            mock.patch.object(bmu, "fetch_cargo_toml_nu_dep", return_value="0.112.0"),
        ):
            did_bump, reason, summary = bmu.bump_entry(entry)

        self.assertTrue(did_bump, reason)
        self.assertIsNotNone(summary)
        m_moved.assert_called_once_with("example/nu_plugin_demo", "v0.2.0", "a" * 40)
        m_tags.assert_called_once_with("example/nu_plugin_demo")
        self.assertEqual(entry["tag"], "v0.3.0")
        self.assertEqual(entry["version"], "0.3.0")
        self.assertEqual(entry["source_commit"], "b" * 40)
        self.assertEqual(summary["new_commit"], "b" * 40)
        self.assertEqual(summary["repo"], "example/nu_plugin_demo")
        self.assertEqual(entry["nu_version"], ">=0.112.0 <0.113.0")
        self.assertEqual(entry["verified_with"], [])

    def test_refuses_when_upstream_nu_dependency_missing(self):
        entry = self._sample_entry()
        did_bump, reason, summary = self._run_bump_with_mocked_upstream(
            entry, "v0.3.0", "b" * 40, None
        )
        self.assertFalse(did_bump)
        self.assertIsNone(summary)
        self.assertIn("could not determine upstream Nu dependency", reason)

    def test_skips_commit_snapshot_entries(self):
        entry = self._sample_entry()
        entry["intake_mode"] = "commit-snapshot"
        entry["tag"] = None
        did_bump, reason, summary = bmu.bump_entry(entry)
        self.assertFalse(did_bump)
        self.assertIsNone(summary)
        self.assertIn("commit-snapshot", reason)

    def test_skips_major_version_bump(self):
        entry = self._sample_entry()
        with (
            mock.patch.object(bmu, "_check_tag_moved", return_value=False),
            mock.patch.object(
                bmu,
                "fetch_latest_tags",
                return_value=[{"name": "v1.0.0", "commit_sha": "c" * 40}],
            ),
        ):
            did_bump, reason, _ = bmu.bump_entry(entry)
        self.assertFalse(did_bump)
        self.assertIn("major version bump", reason)

    def test_refuses_when_current_tag_moved(self):
        entry = self._sample_entry()
        with mock.patch.object(bmu, "_check_tag_moved", return_value=True):
            did_bump, reason, _ = bmu.bump_entry(entry)
        self.assertFalse(did_bump)
        self.assertIn("moved upstream", reason)

    def test_refuses_nu_dependency_downgrade(self):
        entry = self._sample_entry()
        entry["nu_version"] = ">=0.112.0 <0.113.0"
        did_bump, reason, summary = self._run_bump_with_mocked_upstream(
            entry, "v0.2.1", "d" * 40, "0.111.0"
        )
        self.assertFalse(did_bump)
        self.assertIsNone(summary)
        self.assertIn("downgrades", reason)

    def test_sanitizes_stale_build_run_exclude_reason_on_bump(self):
        entry = self._sample_entry()
        entry["exclude_targets"] = ["aarch64-unknown-linux-gnu"]
        entry["exclude_reason"] = (
            "linux aarch64 cross: openssl fails; the remaining 3 targets are green on build run 30604641151"
        )
        new_sha = "c" * 40
        did_bump, reason, summary = self._run_bump_with_mocked_upstream(
            entry, "v0.3.0", new_sha, "0.112.0"
        )
        self.assertTrue(did_bump, reason)
        self.assertEqual(entry["exclude_reason"], "linux aarch64 cross: openssl fails")

    def test_sanitize_preserves_negated_verification_reasons(self):
        for reason in (
            "unverified on run 42",
            "not verified on run 42",
            "not green on run 42",
        ):
            self.assertEqual(bmu._sanitize_exclude_reason_on_bump(reason), reason)

    def test_sanitize_removes_remaining_clause_without_count(self):
        self.assertEqual(
            bmu._sanitize_exclude_reason_on_bump(
                "the remaining targets are green on build run 123"
            ),
            "",
        )

    def test_sanitize_collapses_separators_after_removal(self):
        self.assertEqual(
            bmu._sanitize_exclude_reason_on_bump(
                "linux aarch64 cross, targets are green on build run 1, openssl fails"
            ),
            "linux aarch64 cross, openssl fails",
        )

    def test_apply_bump_drops_empty_exclude_reason(self):
        entry = self._sample_entry()
        entry["exclude_reason"] = "targets are green on build run 7"
        candidate = bmu.BumpCandidate(
            new_ver=(0, 3, 0),
            newest_tag="v0.3.0",
            new_sha="c" * 40,
            new_nu_str=">=0.112.0 <0.113.0",
        )
        bmu._apply_bump_to_entry(entry, candidate)
        self.assertNotIn("exclude_reason", entry)


if __name__ == "__main__":
    unittest.main()
