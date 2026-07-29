#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
SAFETY = (ROOT / ".github" / "workflows" / "repo-safety.yml").read_text(encoding="utf-8")
WORKFLOW_DIR = ROOT / ".github" / "workflows"
WORKFLOW_PATHS = sorted({*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")})
WORKFLOWS = [path.read_text(encoding="utf-8") for path in WORKFLOW_PATHS]
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
PINNED_SHA = re.compile(r"^[0-9a-f]{40}$")


class WorkflowSafetyTests(unittest.TestCase):
    def test_publication_is_manual_dispatch_only(self):
        """
        Verify that publication is triggered only by a manually dispatched workflow with the required filter configuration.
        """
        trigger_block = BUILD.split("permissions:", 1)[0]
        self.assertIn("  workflow_dispatch:\n", trigger_block)
        self.assertNotIn("  pull_request:\n", trigger_block)
        self.assertNotIn("  push:\n", trigger_block)
        self.assertRegex(trigger_block, r"only:\n\s+description:.*\n\s+required: true")

    def test_every_action_is_pinned_to_a_commit(self):
        """
        Verify that every GitHub Action reference in each workflow is pinned to a 40-character commit SHA.
        """
        for workflow in WORKFLOWS:
            refs = re.findall(r"^\s*-?\s*uses:\s*[^\s@]+@([^\s#]+)", workflow, re.MULTILINE)
            self.assertTrue(all(PINNED_SHA.fullmatch(ref) for ref in refs), refs)

    def test_publication_shell_never_interpolates_expressions(self):
        """Keep workflow expressions in env/with fields, never executable shell text."""
        lines = BUILD.splitlines()
        shell_lines: list[str] = []
        for index, line in enumerate(lines):
            match = re.match(r"^(\s*)run:\s*(.*)$", line)
            if match is None:
                continue
            indent = len(match.group(1))
            remainder = match.group(2)
            if remainder not in ("|", ">-", ""):
                shell_lines.append(remainder)
            for body_line in lines[index + 1 :]:
                if body_line.strip() and len(body_line) - len(body_line.lstrip()) <= indent:
                    break
                shell_lines.append(body_line)
        self.assertNotIn("${{", "\n".join(shell_lines))

    def test_only_release_job_can_write_contents(self):
        global_permissions, jobs = BUILD.split("jobs:", 1)
        self.assertIn("permissions:\n  contents: read", global_permissions)
        self.assertEqual(BUILD.count("contents: write"), 1)
        release_job = jobs.split("  release:\n", 1)[1]
        self.assertIn("    permissions:\n      contents: write", release_job)
        self.assertNotIn("contents: write", SAFETY)
        self.assertNotIn("action-gh-release", SAFETY)

    def test_macos_uses_supported_runners(self):
        """Keep the executable matrix and manifest metadata on current macOS runners."""
        self.assertNotIn('"os": "macos-13"', BUILD)
        self.assertNotIn('"os": "macos-14"', BUILD)
        self.assertIn('"os": "macos-15-intel"', BUILD)
        self.assertIn('"os": "macos-15"', BUILD)
        self.assertEqual(
            MANIFEST["target_runner_map"]["x86_64-apple-darwin"],
            "macos-15-intel",
        )
        self.assertEqual(
            MANIFEST["target_runner_map"]["aarch64-apple-darwin"],
            "macos-15",
        )


if __name__ == "__main__":
    unittest.main()
