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
        entry["repo"] = "example/nu_plugin_demo"
        with (
            mock.patch.object(bmu, "_check_tag_moved", return_value=False),
            mock.patch.object(
                bmu,
                "fetch_latest_tags",
                return_value=[{"name": "v0.3.0", "commit_sha": "b" * 40}],
            ),
            mock.patch.object(bmu, "resolve_tag_commit", return_value="b" * 40),
            mock.patch.object(bmu, "fetch_cargo_toml_nu_dep", return_value=None),
        ):
            did_bump, reason, summary = bmu.bump_entry(entry)
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
        entry["repo"] = "example/nu_plugin_demo"
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
        entry["repo"] = "example/nu_plugin_demo"
        with mock.patch.object(bmu, "_check_tag_moved", return_value=True):
            did_bump, reason, _ = bmu.bump_entry(entry)
        self.assertFalse(did_bump)
        self.assertIn("moved upstream", reason)

    def test_refuses_nu_dependency_downgrade(self):
        entry = self._sample_entry()
        entry["repo"] = "example/nu_plugin_demo"
        entry["nu_version"] = ">=0.112.0 <0.113.0"
        with (
            mock.patch.object(bmu, "_check_tag_moved", return_value=False),
            mock.patch.object(
                bmu,
                "fetch_latest_tags",
                return_value=[{"name": "v0.2.1", "commit_sha": "d" * 40}],
            ),
            mock.patch.object(bmu, "resolve_tag_commit", return_value="d" * 40),
            mock.patch.object(bmu, "fetch_cargo_toml_nu_dep", return_value="0.111.0"),
        ):
            did_bump, reason, _ = bmu.bump_entry(entry)
        self.assertFalse(did_bump)
        self.assertIn("downgrades", reason)


if __name__ == "__main__":
    unittest.main()
