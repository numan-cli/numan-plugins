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


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BuildSpecSourceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
