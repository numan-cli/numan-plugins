#!/usr/bin/env python3
"""Unit checks that gen_spec emits source provenance."""

from __future__ import annotations

import importlib.util
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "gen_spec.py"


def load_gen_spec():
    spec = importlib.util.spec_from_file_location("gen_spec", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class BuildSpecSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gs = load_gen_spec()

    def test_emits_source_from_manifest_entry(self):
        entry = {
            "owner": "cptpiepmatz",
            "name": "nu_plugin_highlight",
            "plugin_bin": "nu_plugin_highlight",
            "repo": "cptpiepmatz/nu-plugin-highlight",
            "tag": "v1.4.15+0.113.1",
            "source_commit": "c5454221668342bf1770f3793a13d3bd8bcbfea0",
            "version": "1.4.15",
            "nu_version": ">=0.113.0 <0.114.0",
            "verified_with": ["0.113.1"],
            "description": "Syntax highlighting.",
            "tags": ["plugin", "highlight"],
        }
        rows = [
            {
                "target": "x86_64-unknown-linux-gnu",
                "filename": "nu_plugin_highlight-1.4.15-x86_64-unknown-linux-gnu.tar.gz",
                "sha256": "a" * 64,
                "exe": "nu_plugin_highlight",
            }
        ]
        out = self.gs.build_spec(
            entry,
            rows,
            "https://github.com/tonythethompson/numan-plugins/releases/download/nu_plugin_highlight-1.4.15",
            ["x86_64-unknown-linux-gnu"],
        )
        self.assertEqual(
            out["source"],
            {
                "git": "https://github.com/cptpiepmatz/nu-plugin-highlight",
                "rev": "c5454221668342bf1770f3793a13d3bd8bcbfea0",
                "cargo_name": "nu_plugin_highlight",
            },
        )
        self.assertEqual(out["repo"], "https://github.com/cptpiepmatz/nu-plugin-highlight")

    def test_derive_snapshot_version(self):
        self.assertEqual(
            self.gs.derive_snapshot_version("5a1ca2a5ceba60108a4ca6d45ec18d213abb5227", "20260809"),
            "0.0.0-snapshot.20260809.5a1ca2a",
        )

    def test_commit_snapshot_entry_emits_derived_version_and_provenance(self):
        entry = {
            "owner": "euphrasiologist",
            "name": "nu_plugin_plot",
            "plugin_bin": "nu_plugin_plot",
            "repo": "Euphrasiologist/nu_plugin_plot",
            "tag": None,
            "intake_mode": "commit-snapshot",
            "source_commit": "5a1ca2a5ceba60108a4ca6d45ec18d213abb5227",
            "version": "0.0.0",
            "nu_version": ">=0.114.0 <0.115.0",
            "verified_with": [],
            "description": "Plot graphs in nushell using numerical lists.",
            "tags": ["plugin", "plot"],
        }
        rows = [
            {
                "target": "x86_64-unknown-linux-gnu",
                "filename": "nu_plugin_plot-x86_64-unknown-linux-gnu.tar.gz",
                "sha256": "a" * 64,
                "exe": "nu_plugin_plot",
            }
        ]
        out = self.gs.build_spec(
            entry,
            rows,
            "https://github.com/tonythethompson/numan-plugins/releases/download/nu_plugin_plot-snapshot",
            ["x86_64-unknown-linux-gnu"],
            snapshot_date="20260809",
        )
        self.assertEqual(out["version"], "0.0.0-snapshot.20260809.5a1ca2a")
        self.assertEqual(out["provenance"], "commit-snapshot")
        self.assertIn("commit snapshot, no tagged release", out["description"])

    def test_tagged_entry_has_no_provenance_field(self):
        entry = {
            "owner": "o",
            "name": "p",
            "plugin_bin": "p",
            "repo": "o/p",
            "tag": "v1",
            "source_commit": "1" * 40,
            "version": "1.0.0",
            "nu_version": "*",
            "verified_with": [],
            "description": "p",
            "tags": ["plugin"],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        out = self.gs.build_spec(entry, rows, "https://example.invalid", ["linux"])
        self.assertNotIn("provenance", out)

    def test_fork_entry_emits_source_upstream_and_description_note(self):
        entry = {
            "owner": "numan-maintained",
            "name": "nu_plugin_clipboard",
            "plugin_bin": "nu_plugin_clipboard",
            "repo": "numan-maintained/nu_plugin_clipboard",
            "upstream_repo": "FMotalleb/nu_plugin_clipboard",
            "tag": "numan/nu-0.114-v0.110.0",
            "source_commit": "2" * 40,
            "version": "0.110.0",
            "nu_version": ">=0.114.0 <0.115.0",
            "verified_with": ["0.114.1"],
            "description": "Clipboard access for Nushell.",
            "tags": ["plugin", "clipboard"],
        }
        rows = [
            {
                "target": "x86_64-unknown-linux-gnu",
                "filename": "nu_plugin_clipboard-0.110.0-x86_64-unknown-linux-gnu.tar.gz",
                "sha256": "a" * 64,
                "exe": "nu_plugin_clipboard",
            }
        ]
        out = self.gs.build_spec(
            entry,
            rows,
            "https://github.com/tonythethompson/numan-plugins/releases/download/nu_plugin_clipboard-0.110.0",
            ["x86_64-unknown-linux-gnu"],
        )
        self.assertEqual(
            out["source"]["upstream"], "https://github.com/FMotalleb/nu_plugin_clipboard"
        )
        self.assertIn("(numan-maintained fork; upstream: FMotalleb/nu_plugin_clipboard)", out["description"])

    def test_numan_maintained_requires_upstream_repo(self):
        entry = {
            "owner": "numan-maintained",
            "name": "nu_plugin_clipboard",
            "plugin_bin": "nu_plugin_clipboard",
            "repo": "numan-maintained/nu_plugin_clipboard",
            "tag": "numan/nu-0.114-v0.110.0",
            "source_commit": "2" * 40,
            "version": "0.110.0",
            "nu_version": ">=0.114.0 <0.115.0",
            "verified_with": ["0.114.1"],
            "description": "Clipboard access for Nushell.",
            "tags": ["plugin", "clipboard"],
        }
        rows = [
            {
                "target": "x86_64-unknown-linux-gnu",
                "filename": "nu_plugin_clipboard-0.110.0-x86_64-unknown-linux-gnu.tar.gz",
                "sha256": "a" * 64,
                "exe": "nu_plugin_clipboard",
            }
        ]
        with self.assertRaisesRegex(ValueError, "requires upstream_repo"):
            self.gs.build_spec(
                entry,
                rows,
                "https://github.com/tonythethompson/numan-plugins/releases/download/nu_plugin_clipboard-0.110.0",
                ["x86_64-unknown-linux-gnu"],
            )
    def test_rejects_self_referential_upstream_repo(self):
        entry = {
            "owner": "numan-maintained",
            "name": "nu_plugin_clipboard",
            "plugin_bin": "nu_plugin_clipboard",
            "repo": "numan-maintained/nu_plugin_clipboard",
            "upstream_repo": "numan-maintained/nu_plugin_clipboard",
            "tag": "numan/nu-0.114-v0.110.0",
            "source_commit": "2" * 40,
            "version": "0.110.0",
            "nu_version": ">=0.114.0 <0.115.0",
            "verified_with": ["0.114.1"],
            "description": "Clipboard access for Nushell.",
            "tags": ["plugin", "clipboard"],
        }
        rows = [
            {
                "target": "x86_64-unknown-linux-gnu",
                "filename": "nu_plugin_clipboard-0.110.0-x86_64-unknown-linux-gnu.tar.gz",
                "sha256": "a" * 64,
                "exe": "nu_plugin_clipboard",
            }
        ]
        with self.assertRaisesRegex(ValueError, "must not be the same as repo"):
            self.gs.build_spec(
                entry,
                rows,
                "https://github.com/tonythethompson/numan-plugins/releases/download/nu_plugin_clipboard-0.110.0",
                ["x86_64-unknown-linux-gnu"],
            )

    def test_rejects_blank_upstream_repo(self):
        entry = {
            "owner": "numan-maintained",
            "name": "nu_plugin_clipboard",
            "plugin_bin": "nu_plugin_clipboard",
            "repo": "numan-maintained/nu_plugin_clipboard",
            "upstream_repo": "",
            "tag": "v1",
            "source_commit": "2" * 40,
            "version": "0.110.0",
            "nu_version": "*",
            "verified_with": ["0.114.1"],
            "description": "desc",
            "tags": [],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        with self.assertRaisesRegex(ValueError, "non-empty string"):
            self.gs.build_spec(entry, rows, "https://example.invalid", ["linux"])

    def test_rejects_malformed_upstream_repo(self):
        entry = {
            "owner": "numan-maintained",
            "name": "nu_plugin_clipboard",
            "plugin_bin": "nu_plugin_clipboard",
            "repo": "numan-maintained/nu_plugin_clipboard",
            "upstream_repo": "https://github.com/FMotalleb/nu_plugin_clipboard",
            "tag": "v1",
            "source_commit": "2" * 40,
            "version": "0.110.0",
            "nu_version": "*",
            "verified_with": ["0.114.1"],
            "description": "desc",
            "tags": [],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        with self.assertRaisesRegex(ValueError, "must be 'owner/name'"):
            self.gs.build_spec(entry, rows, "https://example.invalid", ["linux"])

    def test_rejects_numan_maintained_without_upstream_repo(self):
        entry = {
            "owner": "numan-maintained",
            "name": "nu_plugin_clipboard",
            "plugin_bin": "nu_plugin_clipboard",
            "repo": "numan-maintained/nu_plugin_clipboard",
            "tag": "v1",
            "source_commit": "2" * 40,
            "version": "0.110.0",
            "nu_version": "*",
            "verified_with": ["0.114.1"],
            "description": "desc",
            "tags": [],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        with self.assertRaisesRegex(ValueError, "requires upstream_repo"):
            self.gs.build_spec(entry, rows, "https://example.invalid", ["linux"])

    def test_rejects_upstream_repo_without_numan_maintained_owner(self):
        entry = {
            "owner": "cptpiepmatz",
            "name": "nu_plugin_highlight",
            "plugin_bin": "nu_plugin_highlight",
            "repo": "cptpiepmatz/nu-plugin-highlight",
            "upstream_repo": "other/nu-plugin-highlight",
            "tag": "v1",
            "source_commit": "3" * 40,
            "version": "1.0.0",
            "nu_version": "*",
            "verified_with": ["0.113.1"],
            "description": "desc",
            "tags": [],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        with self.assertRaisesRegex(ValueError, "requires owner 'numan-maintained'"):
            self.gs.build_spec(entry, rows, "https://example.invalid", ["linux"])

    def test_non_fork_entry_omits_source_upstream(self):
        entry = {
            "owner": "cptpiepmatz",
            "name": "nu_plugin_highlight",
            "plugin_bin": "nu_plugin_highlight",
            "repo": "cptpiepmatz/nu-plugin-highlight",
            "tag": "v1.4.15",
            "source_commit": "3" * 40,
            "version": "1.4.15",
            "nu_version": ">=0.113.0 <0.114.0",
            "verified_with": ["0.113.1"],
            "description": "Syntax highlighting.",
            "tags": ["plugin"],
        }
        rows = [
            {
                "target": "x86_64-unknown-linux-gnu",
                "filename": "nu_plugin_highlight-1.4.15-x86_64-unknown-linux-gnu.tar.gz",
                "sha256": "a" * 64,
                "exe": "nu_plugin_highlight",
            }
        ]
        out = self.gs.build_spec(
            entry, rows, "https://example.invalid", ["x86_64-unknown-linux-gnu"]
        )
        self.assertNotIn("upstream", out["source"])
        self.assertNotIn("numan-maintained fork", out["description"])

    def test_rejects_missing_expected_target(self):
        entry = {
            "owner": "o",
            "name": "p",
            "plugin_bin": "p",
            "repo": "o/p",
            "tag": "v1",
            "source_commit": "1" * 40,
            "version": "1.0.0",
            "nu_version": "*",
            "verified_with": [],
            "description": "p",
            "tags": ["plugin"],
        }
        with self.assertRaisesRegex(ValueError, "missing targets"):
            self.gs.build_spec(entry, [], "https://example.invalid", ["linux"])

    def test_partial_emits_spec_with_only_succeeded_targets(self):
        entry = {
            "owner": "o",
            "name": "p",
            "plugin_bin": "p",
            "repo": "o/p",
            "tag": "v1",
            "source_commit": "1" * 40,
            "version": "1.0.0",
            "nu_version": "*",
            "verified_with": [],
            "description": "p",
            "tags": ["plugin"],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        out = self.gs.build_spec(
            entry, rows, "https://example.invalid", ["linux", "windows"], partial=True
        )
        self.assertEqual(list(out["artifact"]["targets"]), ["linux"])

    def test_partial_still_rejects_zero_targets(self):
        entry = {
            "owner": "o",
            "name": "p",
            "plugin_bin": "p",
            "repo": "o/p",
            "tag": "v1",
            "source_commit": "1" * 40,
            "version": "1.0.0",
            "nu_version": "*",
            "verified_with": [],
            "description": "p",
            "tags": ["plugin"],
        }
        with self.assertRaisesRegex(ValueError, "at least one target must succeed"):
            self.gs.build_spec(entry, [], "https://example.invalid", ["linux"], partial=True)

    def test_partial_rejects_zero_targets_with_zero_expected(self):
        entry = {
            "owner": "o",
            "name": "p",
            "plugin_bin": "p",
            "repo": "o/p",
            "tag": "v1",
            "source_commit": "1" * 40,
            "version": "1.0.0",
            "nu_version": "*",
            "verified_with": [],
            "description": "p",
            "tags": ["plugin"],
        }
        with self.assertRaisesRegex(ValueError, "at least one target must succeed"):
            self.gs.build_spec(entry, [], "https://example.invalid", [], partial=True)

    def test_partial_still_rejects_unexpected_target(self):
        entry = {
            "owner": "o",
            "name": "p",
            "plugin_bin": "p",
            "repo": "o/p",
            "tag": "v1",
            "source_commit": "1" * 40,
            "version": "1.0.0",
            "nu_version": "*",
            "verified_with": [],
            "description": "p",
            "tags": ["plugin"],
        }
        rows = [{"target": "solaris", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        with self.assertRaisesRegex(ValueError, "unexpected targets"):
            self.gs.build_spec(entry, rows, "https://example.invalid", ["linux"], partial=True)

    def test_rejects_duplicate_packaged_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = Path(tmp) / "packaged.tsv"
            records.write_text(
                "PACKAGED\tlinux\ta.tar.gz\t" + "a" * 64 + "\tplugin\n"
                "PACKAGED\tlinux\tb.tar.gz\t" + "b" * 64 + "\tplugin\n",
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                self.gs.parse_packaged(records)

    def test_verifies_packaged_asset_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = root / "p.zip"
            asset.write_bytes(b"package")
            digest = hashlib.sha256(b"package").hexdigest()
            rows = [{"filename": "p.zip", "sha256": digest, "target": "win", "exe": "p.exe"}]
            self.gs.verify_packaged_assets(rows, root)
            asset.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                self.gs.verify_packaged_assets(rows, root)

    def test_rejects_orphan_assets_without_package_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kept = root / "kept.tar.gz"
            kept.write_bytes(b"kept")
            orphan = root / "orphan.tar.gz"
            orphan.write_bytes(b"orphan")
            rows = [
                {
                    "filename": "kept.tar.gz",
                    "sha256": hashlib.sha256(b"kept").hexdigest(),
                    "target": "linux",
                    "exe": "p",
                }
            ]
            with self.assertRaisesRegex(ValueError, "orphan assets without package records"):
                self.gs.verify_packaged_assets(rows, root)

    def test_rejects_missing_assets_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_path = root / "nonexistent"
            rows = [
                {
                    "filename": "package.tar.gz",
                    "sha256": "a" * 64,
                    "target": "linux",
                    "exe": "p",
                }
            ]
            with self.assertRaisesRegex(ValueError, "assets dir not found"):
                self.gs.verify_packaged_assets(rows, missing_path)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BuildSpecSourceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
