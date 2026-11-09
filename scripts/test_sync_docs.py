#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "sync_docs.py"


def load_mod():
    spec = importlib.util.spec_from_file_location("sync_docs", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class SyncDocsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_mod()

    def test_sync_roadmap_rewrites_wrapped_count(self):
        text = (
            "Wave 1 includes Nu 0.113.1 and Nu 0.112.2. "
            "`manifest.json` `active[]` currently\n  holds 33 plugins.\n"
        )
        new_text, changed = self.mod.sync_roadmap(text, 34)
        self.assertTrue(changed)
        self.assertIn("`manifest.json` `active[]` currently\n  holds 34 plugins.", new_text)

    def test_sync_roadmap_no_change_when_count_matches(self):
        text = "`manifest.json` `active[]` currently\n  holds 33 plugins.\n"
        new_text, changed = self.mod.sync_roadmap(text, 33)
        self.assertFalse(changed)
        self.assertEqual(new_text, text)

    def test_sync_roadmap_raises_when_anchor_absent(self):
        with self.assertRaisesRegex(ValueError, "active\\[\\] currently holds"):
            self.mod.sync_roadmap("no count sentence here\n", 33)

    def test_sync_afterword_preserves_matching_word(self):
        lines = ["The six commit snapshots above passed the lifecycle.\n"]
        result = self.mod._sync_afterword(lines, 6)
        self.assertEqual(result, lines)

    def test_sync_afterword_rewrites_drifted_count(self):
        lines = ["The six commit snapshots above passed the lifecycle.\n"]
        result = self.mod._sync_afterword(lines, 7)
        self.assertEqual(result, ["The 7 commit snapshots above passed the lifecycle.\n"])

    def test_sync_afterword_raises_when_sentence_missing_and_expected(self):
        with self.assertRaisesRegex(ValueError, "commit snapshots above passed"):
            self.mod._sync_afterword(["No snapshot narrative here.\n"], 6)

    def test_sync_afterword_ignores_missing_sentence_when_count_zero(self):
        lines = ["No snapshot narrative here.\n"]
        result = self.mod._sync_afterword(lines, 0)
        self.assertEqual(result, lines)

    def test_snapshot_count_repl_preserves_word_above_ten(self):
        match = self.mod.SNAPSHOT_COUNT_RE.search("The eleven commit snapshots above passed")
        self.assertIsNotNone(match)
        self.assertEqual(self.mod._snapshot_count_repl(match, 11), match.group(0))

    def test_snapshot_count_repl_rewrites_digit_count(self):
        match = self.mod.SNAPSHOT_COUNT_RE.search("The six commit snapshots above passed")
        self.assertIsNotNone(match)
        self.assertEqual(self.mod._snapshot_count_repl(match, 7), "The 7 commit snapshots above passed")

    def test_sync_readme_updates_active_and_pending(self):
        readme = (
            "# Title\n\n"
            "## Currently active\n\n"
            "- `acme/plug_a` @ `v1.0.0` → `nu_plugin_a` 1.0.0\n\n"
            "The 0 commit snapshots above passed the lifecycle.\n\n"
            "## Pending first build\n\n"
            "Preamble narrative line.\n\n"
            "- `acme/plug_b` @ `v0.9.0` → `nu_plugin_b` 0.9.0 _(old note)_\n\n"
            "## Footer\n\n"
            "Footer content.\n"
        )
        new_active = ["- `acme/plug_a` @ `v1.0.1` → `nu_plugin_a` 1.0.1"]
        new_pending = ["- `acme/plug_b` @ `v1.0.0` → `nu_plugin_b` 1.0.0 _(updated note)_"]
        new_text, changed = self.mod.sync_readme(
            readme,
            expected_active=new_active,
            expected_pending=new_pending,
            snapshot_count=0,
        )
        self.assertTrue(changed)
        self.assertIn("- `acme/plug_a` @ `v1.0.1` → `nu_plugin_a` 1.0.1", new_text)
        self.assertIn("- `acme/plug_b` @ `v1.0.0` → `nu_plugin_b` 1.0.0 _(updated note)_", new_text)
        self.assertIn("Preamble narrative line.", new_text)

    def test_resolve_pending_notes_detects_bump_from_active(self):
        active_entries = [
            {"name": "nu_plugin_hcl", "version": "0.116.1", "verified_with": []},
            {"name": "nu_plugin_dns", "version": "4.0.14", "verified_with": []},
            {"name": "nu_plugin_custom", "version": "1.0.0", "verified_with": []},
        ]
        active_versions = {"nu_plugin_hcl": "0.114.1"}
        pending_versions = {"nu_plugin_dns": "4.0.11", "nu_plugin_custom": "1.0.0"}
        pending_notes = {
            "nu_plugin_dns": "_(bumped from 4.0.10)_",
            "nu_plugin_custom": "_(workspace member crate)_",
        }
        resolved = self.mod.resolve_pending_notes(
            active_entries, active_versions, pending_versions, pending_notes
        )
        self.assertEqual(resolved["nu_plugin_hcl"], "_(bumped from 0.114.1)_")
        self.assertEqual(resolved["nu_plugin_dns"], "_(bumped from 4.0.11)_")
        self.assertEqual(resolved["nu_plugin_custom"], "_(workspace member crate)_")


if __name__ == "__main__":
    unittest.main()
