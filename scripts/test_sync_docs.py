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


if __name__ == "__main__":
    unittest.main()