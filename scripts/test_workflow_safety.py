#!/usr/bin/env python3

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
SAFETY = (ROOT / ".github" / "workflows" / "repo-safety.yml").read_text(encoding="utf-8")
WORKFLOW_DIR = ROOT / ".github" / "workflows"
WORKFLOW_PATHS = sorted({*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")})
WORKFLOWS = [path.read_text(encoding="utf-8") for path in WORKFLOW_PATHS]
PINNED_SHA = re.compile(r"^[0-9a-f]{40}$")


class WorkflowSafetyTests(unittest.TestCase):
    def test_publication_is_manual_dispatch_only(self):
        trigger_block = BUILD.split("permissions:", 1)[0]
        self.assertIn("  workflow_dispatch:\n", trigger_block)
        self.assertNotIn("  pull_request:\n", trigger_block)
        self.assertNotIn("  push:\n", trigger_block)
        self.assertRegex(trigger_block, r"only:\n\s+description:.*\n\s+required: true")

    def test_every_action_is_pinned_to_a_commit(self):
        for workflow in WORKFLOWS:
            refs = re.findall(r"^\s*-?\s*uses:\s*[^\s@]+@([^\s#]+)", workflow, re.MULTILINE)
            self.assertTrue(all(PINNED_SHA.fullmatch(ref) for ref in refs), refs)

    def test_only_release_job_can_write_contents(self):
        global_permissions, jobs = BUILD.split("jobs:", 1)
        self.assertIn("permissions:\n  contents: read", global_permissions)
        self.assertEqual(BUILD.count("contents: write"), 1)
        release_job = jobs.split("  release:\n", 1)[1]
        self.assertIn("    permissions:\n      contents: write", release_job)
        self.assertNotIn("contents: write", SAFETY)
        self.assertNotIn("action-gh-release", SAFETY)


if __name__ == "__main__":
    unittest.main()
