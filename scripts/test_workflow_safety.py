#!/usr/bin/env python3

from __future__ import annotations

import ast
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
TARGETS_ASSIGNMENT = re.compile(
    r"^(\s*)TARGETS\s*=\s*(\[[\s\S]*?\n\1\])",
    re.MULTILINE,
)


def workflow_targets(workflow: str) -> list[dict[str, object]]:
    """
    Parse the ``TARGETS`` assignment from a build workflow.

    Expects ``TARGETS`` to be a Python list of dicts, each with at least
    ``triple`` (Rust target triple), ``os`` (GitHub runner label), and
    ``cross`` (bool, whether the job cross-compiles).

    Parameters:
        workflow: Build workflow text containing a ``TARGETS`` assignment.

    Returns:
        The parsed target definitions in declaration order.

    Raises:
        AssertionError: If the ``TARGETS`` assignment is missing or is not a list.
    """
    match = TARGETS_ASSIGNMENT.search(workflow)
    if match is None:
        raise AssertionError("TARGETS assignment not found in build workflow")
    parsed = ast.literal_eval(match.group(2))
    if not isinstance(parsed, list):
        raise AssertionError(f"TARGETS must be a list, got {type(parsed).__name__}")
    return parsed


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

    def test_release_upload_uses_claimed_release_id(self):
        """Avoid softprops creating a second draft when the tag is briefly undiscoverable."""
        self.assertNotIn("softprops/action-gh-release", BUILD)
        self.assertIn("release_transaction.py upload", BUILD)
        self.assertIn("--release-id \"$CLAIMED_RELEASE_ID\"", BUILD)

    def test_matrix_env_shell_steps_force_bash(self):
        """Steps that expand $MATRIX_* must use bash so Windows pwsh does not empty them."""
        lines = BUILD.splitlines()
        for index, line in enumerate(lines):
            if not re.match(r"^\s+- name:\s+", line):
                continue
            block: list[str] = [line]
            base_indent = len(line) - len(line.lstrip())
            for body_line in lines[index + 1 :]:
                if body_line.strip() and len(body_line) - len(body_line.lstrip()) <= base_indent:
                    break
                block.append(body_line)
            text = "\n".join(block)
            if "$MATRIX_" not in text:
                continue
            self.assertIn(
                "shell: bash",
                text,
                f"step must force bash when expanding MATRIX env vars:\n{text}",
            )

    def test_macos_uses_supported_runners(self):
        """Keep the executable matrix and manifest metadata on current macOS runners."""
        targets = workflow_targets(BUILD)
        by_triple = {entry["triple"]: entry["os"] for entry in targets}
        self.assertEqual(by_triple["x86_64-apple-darwin"], "macos-15-intel")
        self.assertEqual(by_triple["aarch64-apple-darwin"], "macos-15")
        self.assertNotIn("macos-13", by_triple.values())
        self.assertNotIn("macos-14", by_triple.values())
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
