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


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BuildSpecSourceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
