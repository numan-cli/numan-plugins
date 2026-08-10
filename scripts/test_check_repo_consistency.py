#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_repo_consistency.py"


def load_mod():
    spec = importlib.util.spec_from_file_location("check_repo_consistency", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class CheckRepoConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_mod()

    def _write(self, root: Path, *, manifest: dict, backlog: dict, readme_active: list[str]):
        (root / "docs").mkdir(parents=True, exist_ok=True)
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (root / "docs" / "backlog.json").write_text(json.dumps(backlog), encoding="utf-8")
        body = ["# Demo", "", "## Currently active", ""]
        body.extend(readme_active)
        body.extend(["", "## Next", "", "x"])
        (root / "README.md").write_text("\n".join(body) + "\n", encoding="utf-8")

    def test_readme_must_match_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = [
                {
                    "repo": "acme/plug",
                    "name": "nu_plugin_plug",
                    "tag": "v1.0.0",
                    "version": "1.0.0",
                }
            ]
            self._write(
                root,
                manifest={"active": active, "backlog_note": "ok"},
                backlog={"plugins": []},
                readme_active=["- `other/plug` @ `v1.0.0` → `nu_plugin_plug` 1.0.0"],
            )
            errors = self.mod.check_readme_active(
                root / "manifest.json", root / "README.md"
            )
            self.assertTrue(errors)

    def test_promoted_with_pending_registry_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog = {
                "plugins": [
                    {
                        "name": "nu_plugin_x",
                        "status": "PROMOTED",
                        "backfill_targets": ["0.114"],
                        "c1_note": "pending registry intake",
                    }
                ]
            }
            (root / "docs").mkdir()
            path = root / "docs" / "backlog.json"
            path.write_text(json.dumps(backlog), encoding="utf-8")
            errors = self.mod.check_backlog_promoted(path)
            self.assertEqual(len(errors), 1)

    def test_pr_ref_in_backlog_note_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            backlog = root / "docs" / "backlog.json"
            backlog.parent.mkdir()
            manifest.write_text(
                json.dumps({"backlog_note": "Wave 2 (this PR): demo"}),
                encoding="utf-8",
            )
            backlog.write_text(json.dumps({"note": "ok", "plugins": []}), encoding="utf-8")
            found = self.mod.check_no_pr_refs(manifest, backlog)
            self.assertTrue(any("backlog_note" in item for item in found))

    def test_pr_number_in_c1_note_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backlog = root / "docs" / "backlog.json"
            backlog.parent.mkdir()
            backlog.write_text(
                json.dumps(
                    {
                        "note": "ok",
                        "plugins": [
                            {
                                "name": "nu_plugin_x",
                                "c1_note": "in official registry (numan-registry#45)",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            found = self.mod.check_no_pr_refs(backlog)
            self.assertTrue(any("c1_note" in item for item in found))

    def test_pr_url_in_roadmap_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            roadmap = root / "docs" / "roadmap.md"
            roadmap.parent.mkdir()
            roadmap.write_text(
                "See [intake](https://github.com/tonythethompson/numan-registry/pull/45).\n",
                encoding="utf-8",
            )
            found = self.mod.check_no_pr_refs(roadmap)
            self.assertTrue(found)

    def test_expected_readme_lines_handles_missing_tag(self):
        entry = {
            "repo": "owner/repo",
            "name": "plugin",
            "version": "0.0.0-snapshot.20260809.5a1ca2a",
            "source_commit": "5a1ca2a5ceba60108a4ca6d45ec18d213abb5227",
            "verified_with": ["0.114.1"],
        }
        lines = self.mod.expected_readme_lines([entry])
        self.assertEqual(
            lines,
            ["- `owner/repo` @ `commit 5a1ca2a` → `plugin` 0.0.0-snapshot.20260809.5a1ca2a"],
        )


if __name__ == "__main__":
    unittest.main()
