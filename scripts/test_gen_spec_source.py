#!/usr/bin/env python3
"""Unit checks that gen_spec emits source provenance."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
            "https://github.com/numan-cli/numan-plugins/releases/download/nu_plugin_highlight-1.4.15",
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
            "https://github.com/numan-cli/numan-plugins/releases/download/nu_plugin_plot-snapshot",
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
            "https://github.com/numan-cli/numan-plugins/releases/download/nu_plugin_clipboard-0.110.0",
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
                "https://github.com/numan-cli/numan-plugins/releases/download/nu_plugin_clipboard-0.110.0",
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
                "https://github.com/numan-cli/numan-plugins/releases/download/nu_plugin_clipboard-0.110.0",
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
    def test_load_manifest_entry_missing_name_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.json"
            manifest_path.write_text(
                json.dumps({"active": [{"name": "other"}]}), encoding="utf-8"
            )
            with self.assertRaises(SystemExit):
                self.gs.load_manifest_entry("missing", manifest_path)

    def test_parse_packaged_rejects_malformed_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = Path(tmp) / "packaged.tsv"
            records.write_text("PACKAGED\tlinux\tonly-three-fields\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.gs.parse_packaged(records)

    def test_parse_packaged_rejects_invalid_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = Path(tmp) / "packaged.tsv"
            records.write_text("PACKAGED\tlinux\ta.tar.gz\tnothex\tplugin\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.gs.parse_packaged(records)

    def test_parse_packaged_rejects_no_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = Path(tmp) / "packaged.tsv"
            records.write_text("not a packaged line\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.gs.parse_packaged(records)

    def test_verify_packaged_assets_missing_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [{"filename": "missing.zip", "sha256": "a" * 64, "target": "win", "exe": "p.exe"}]
            with self.assertRaisesRegex(ValueError, "not found"):
                self.gs.verify_packaged_assets(rows, Path(tmp))

    def test_build_spec_rejects_extra_targets(self):
        entry = {
            "owner": "o", "name": "p", "plugin_bin": "p", "repo": "o/p", "tag": "v1",
            "source_commit": "1" * 40, "version": "1.0.0", "nu_version": "*",
            "verified_with": [], "description": "p", "tags": ["plugin"],
        }
        rows = [{"target": "linux", "filename": "a.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        with self.assertRaisesRegex(ValueError, "unexpected targets"):
            self.gs.build_spec(entry, rows, "https://example.invalid", [])

    def test_provisional_emits_evidence_tier_and_omits_verified_with(self):
        entry = {
            "owner": "galuszkak", "name": "nu_plugin_bigquery", "plugin_bin": "nu_plugin_bigquery",
            "repo": "galuszkak/nu_plugin_bigquery", "tag": "v0.3.0",
            "source_commit": "4" * 40, "version": "0.3.0", "nu_version": "*",
            "verified_with": [], "description": "BigQuery access.", "tags": ["plugin"],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        out = self.gs.build_spec(
            entry,
            rows,
            "https://example.invalid",
            ["linux"],
            provisional=True,
            deferral_reason="needs GCP credentials",
        )
        self.assertNotIn("verified_with", out)
        self.assertEqual(out["evidence_tier"], "provisional")
        self.assertEqual(out["deferral_reason"], "needs GCP credentials")
        keys = list(out)
        self.assertEqual(
            keys[keys.index("nu_version") + 1 : keys.index("source")],
            ["evidence_tier", "deferral_reason"],
        )

    def test_provisional_strips_deferral_reason_whitespace(self):
        entry = {
            "owner": "o", "name": "p", "plugin_bin": "p", "repo": "o/p", "tag": "v1",
            "source_commit": "1" * 40, "version": "1.0.0", "nu_version": "*",
            "verified_with": [], "description": "p", "tags": ["plugin"],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        out = self.gs.build_spec(
            entry,
            rows,
            "https://example.invalid",
            ["linux"],
            provisional=True,
            deferral_reason="  needs GCP credentials\n",
        )
        self.assertEqual(out["deferral_reason"], "needs GCP credentials")

    def test_provisional_requires_deferral_reason(self):
        entry = {
            "owner": "o", "name": "p", "plugin_bin": "p", "repo": "o/p", "tag": "v1",
            "source_commit": "1" * 40, "version": "1.0.0", "nu_version": "*",
            "verified_with": [], "description": "p", "tags": ["plugin"],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        with self.assertRaisesRegex(ValueError, "deferral reason"):
            self.gs.build_spec(
                entry, rows, "https://example.invalid", ["linux"], provisional=True
            )

    def test_provisional_rejects_blank_deferral_reason(self):
        entry = {
            "owner": "o", "name": "p", "plugin_bin": "p", "repo": "o/p", "tag": "v1",
            "source_commit": "1" * 40, "version": "1.0.0", "nu_version": "*",
            "verified_with": [], "description": "p", "tags": ["plugin"],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        with self.assertRaisesRegex(ValueError, "deferral reason"):
            self.gs.build_spec(
                entry,
                rows,
                "https://example.invalid",
                ["linux"],
                provisional=True,
                deferral_reason="   \t\n",
            )

    def test_provisional_rejects_entry_with_lifecycle_evidence(self):
        entry = {
            "owner": "o", "name": "p", "plugin_bin": "p", "repo": "o/p", "tag": "v1",
            "source_commit": "1" * 40, "version": "1.0.0", "nu_version": "*",
            "verified_with": ["0.114.1"], "description": "p", "tags": ["plugin"],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        with self.assertRaisesRegex(ValueError, "verified_with"):
            self.gs.build_spec(
                entry,
                rows,
                "https://example.invalid",
                ["linux"],
                provisional=True,
                deferral_reason="needs GCP credentials",
            )

    def test_deferral_reason_without_provisional_is_rejected(self):
        entry = {
            "owner": "o", "name": "p", "plugin_bin": "p", "repo": "o/p", "tag": "v1",
            "source_commit": "1" * 40, "version": "1.0.0", "nu_version": "*",
            "verified_with": [], "description": "p", "tags": ["plugin"],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        with self.assertRaisesRegex(ValueError, "only recorded for provisional"):
            self.gs.build_spec(
                entry,
                rows,
                "https://example.invalid",
                ["linux"],
                deferral_reason="needs GCP credentials",
            )

    def test_non_provisional_spec_keeps_verified_with_only(self):
        entry = {
            "owner": "o", "name": "p", "plugin_bin": "p", "repo": "o/p", "tag": "v1",
            "source_commit": "1" * 40, "version": "1.0.0", "nu_version": "*",
            "verified_with": ["0.114.1"], "description": "p", "tags": ["plugin"],
        }
        rows = [{"target": "linux", "filename": "p.tar.gz", "sha256": "a" * 64, "exe": "p"}]
        out = self.gs.build_spec(entry, rows, "https://example.invalid", ["linux"])
        self.assertEqual(out["verified_with"], ["0.114.1"])
        self.assertNotIn("evidence_tier", out)
        self.assertNotIn("deferral_reason", out)

    def _manifest_entry(self):
        return {
            "owner": "o", "name": "p", "plugin_bin": "p", "repo": "o/p", "tag": "v1",
            "source_commit": "1" * 40, "version": "1.0.0", "nu_version": "*",
            "verified_with": [], "description": "p", "tags": ["plugin"],
        }

    def test_main_success_writes_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "default_targets": ["x86_64-unknown-linux-gnu"],
                        "active": [self._manifest_entry()],
                    }
                ),
                encoding="utf-8",
            )
            assets_dir = root / "assets"
            assets_dir.mkdir()
            asset = assets_dir / "p-1.0.0-linux.tar.gz"
            asset.write_bytes(b"data")
            digest = hashlib.sha256(b"data").hexdigest()
            packaged = root / "packaged.tsv"
            packaged.write_text(
                f"PACKAGED\tx86_64-unknown-linux-gnu\t{asset.name}\t{digest}\tp\n",
                encoding="utf-8",
            )
            out = root / "spec.json"
            argv = [
                "gen_spec.py",
                "--name", "p",
                "--packaged", str(packaged),
                "--assets-dir", str(assets_dir),
                "--release-base", "https://example.invalid/release",
                "--out", str(out),
            ]
            with mock.patch.object(self.gs, "REPO_ROOT", root), mock.patch.object(
                sys, "argv", argv
            ):
                rc = self.gs.main()
            self.assertEqual(rc, 0)
            spec = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(spec["name"], "p")
            self.assertIn("x86_64-unknown-linux-gnu", spec["artifact"]["targets"])

    def test_main_failure_prints_fail_and_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "default_targets": ["x86_64-unknown-linux-gnu"],
                        "active": [self._manifest_entry()],
                    }
                ),
                encoding="utf-8",
            )
            assets_dir = root / "assets"
            assets_dir.mkdir()
            packaged = root / "packaged.tsv"
            packaged.write_text(
                "PACKAGED\tx86_64-unknown-linux-gnu\tmissing.tar.gz\t" + "a" * 64 + "\tp\n",
                encoding="utf-8",
            )
            out = root / "spec.json"
            argv = [
                "gen_spec.py",
                "--name", "p",
                "--packaged", str(packaged),
                "--assets-dir", str(assets_dir),
                "--release-base", "https://example.invalid/release",
                "--out", str(out),
            ]
            with mock.patch.object(self.gs, "REPO_ROOT", root), mock.patch.object(
                sys, "argv", argv
            ):
                rc = self.gs.main()
            self.assertEqual(rc, 1)
            self.assertFalse(out.is_file())

    def test_main_provisional_writes_evidence_tier_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "default_targets": ["x86_64-unknown-linux-gnu"],
                        "active": [self._manifest_entry()],
                    }
                ),
                encoding="utf-8",
            )
            assets_dir = root / "assets"
            assets_dir.mkdir()
            asset = assets_dir / "p-1.0.0-linux.tar.gz"
            asset.write_bytes(b"data")
            digest = hashlib.sha256(b"data").hexdigest()
            packaged = root / "packaged.tsv"
            packaged.write_text(
                f"PACKAGED\tx86_64-unknown-linux-gnu\t{asset.name}\t{digest}\tp\n",
                encoding="utf-8",
            )
            out = root / "spec.json"
            argv = [
                "gen_spec.py",
                "--name", "p",
                "--packaged", str(packaged),
                "--assets-dir", str(assets_dir),
                "--release-base", "https://example.invalid/release",
                "--out", str(out),
                "--provisional",
                "--deferral-reason", "needs GCP credentials",
            ]
            with mock.patch.object(self.gs, "REPO_ROOT", root), mock.patch.object(
                sys, "argv", argv
            ):
                rc = self.gs.main()
            self.assertEqual(rc, 0)
            spec = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(spec["evidence_tier"], "provisional")
            self.assertEqual(spec["deferral_reason"], "needs GCP credentials")
            self.assertNotIn("verified_with", spec)

    def test_main_provisional_without_reason_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "default_targets": ["x86_64-unknown-linux-gnu"],
                        "active": [self._manifest_entry()],
                    }
                ),
                encoding="utf-8",
            )
            assets_dir = root / "assets"
            assets_dir.mkdir()
            asset = assets_dir / "p-1.0.0-linux.tar.gz"
            asset.write_bytes(b"data")
            digest = hashlib.sha256(b"data").hexdigest()
            packaged = root / "packaged.tsv"
            packaged.write_text(
                f"PACKAGED\tx86_64-unknown-linux-gnu\t{asset.name}\t{digest}\tp\n",
                encoding="utf-8",
            )
            out = root / "spec.json"
            argv = [
                "gen_spec.py",
                "--name", "p",
                "--packaged", str(packaged),
                "--assets-dir", str(assets_dir),
                "--release-base", "https://example.invalid/release",
                "--out", str(out),
                "--provisional",
            ]
            with mock.patch.object(self.gs, "REPO_ROOT", root), mock.patch.object(
                sys, "argv", argv
            ):
                rc = self.gs.main()
            self.assertEqual(rc, 1)
            self.assertFalse(out.is_file())


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BuildSpecSourceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
