#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent / "release_transaction.py"


def load_module():
    """
    Load and return the release transaction module from the script path.
    
    Returns:
        module: The dynamically loaded release transaction module.
    """
    spec = importlib.util.spec_from_file_location("release_transaction", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeRunner:
    def __init__(self, responses):
        """Initialize a fake command runner with predefined responses and an empty command history.
        
        Parameters:
            responses: An iterable of response tuples returned for successive commands.
        """
        self.responses = iter(responses)
        self.commands = []

    def __call__(self, command, **kwargs):
        """
        Execute a recorded command and return its predefined subprocess result.
        
        Parameters:
            command: The command to record and associate with the result.
        
        Returns:
            subprocess.CompletedProcess: A result containing the next configured exit code and payload.
        """
        self.commands.append(command)
        code, payload = next(self.responses)
        if isinstance(payload, dict):
            return subprocess.CompletedProcess(command, code, json.dumps(payload), "")
        return subprocess.CompletedProcess(command, code, "", payload)


class ReleaseTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_claim_creates_tag_then_draft(self):
        runner = FakeRunner([(0, {}), (0, {"id": 7, "draft": True, "tag_name": "p-1"})])
        self.assertEqual(self.mod.claim("o/r", "p-1", "a" * 40, "p 1", "body", runner), 7)
        self.assertIn("git/refs", runner.commands[0][4])
        self.assertIn("releases", runner.commands[1][4])

    def test_claim_failure_removes_owned_tag(self):
        runner = FakeRunner([(0, {}), (1, "conflict"), (0, {})])
        with self.assertRaises(RuntimeError):
            self.mod.claim("o/r", "p-1", "a" * 40, "p 1", "body", runner)
        self.assertIn("DELETE", runner.commands[-1])

    def test_finalize_verifies_exact_assets_before_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp) / "p.zip"
            asset.write_bytes(b"asset")
            runner = FakeRunner(
                [
                    (
                        0,
                        {
                            "id": 7,
                            "draft": True,
                            "tag_name": "p-1",
                            "assets": [
                                {
                                    "name": "p.zip",
                                    "size": 5,
                                    "digest": "sha256:"
                                    + hashlib.sha256(b"asset").hexdigest(),
                                }
                            ],
                        },
                    ),
                    (0, {"object": {"sha": "a" * 40}}),
                    (0, {"id": 7, "draft": False}),
                ]
            )
            self.mod.finalize("o/r", 7, "p-1", "a" * 40, Path(tmp), runner)
            self.assertIn("PATCH", runner.commands[-1])

    def test_finalize_rejects_same_size_different_bytes(self):
        """Never publish a same-size remote payload with a different digest."""
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp) / "p.zip"
            asset.write_bytes(b"asset")
            runner = FakeRunner(
                [
                    (
                        0,
                        {
                            "id": 7,
                            "draft": True,
                            "tag_name": "p-1",
                            "assets": [
                                {
                                    "name": "p.zip",
                                    "size": 5,
                                    "digest": "sha256:"
                                    + hashlib.sha256(b"other").hexdigest(),
                                }
                            ],
                        },
                    ),
                    (0, {"object": {"sha": "a" * 40}}),
                ]
            )
            with self.assertRaisesRegex(ValueError, "asset set mismatch"):
                self.mod.finalize("o/r", 7, "p-1", "a" * 40, Path(tmp), runner)
            self.assertFalse(any("PATCH" in command for command in runner.commands))

    def test_finalize_refuses_when_tag_moved(self):
        """Never publish a draft whose tag no longer points at the workflow commit."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "p.zip").write_bytes(b"asset")
            runner = FakeRunner(
                [
                    (0, {"id": 7, "draft": True, "tag_name": "p-1", "assets": []}),
                    (0, {"object": {"sha": "b" * 40}}),
                ]
            )
            with self.assertRaisesRegex(ValueError, "no longer points"):
                self.mod.finalize("o/r", 7, "p-1", "a" * 40, Path(tmp), runner)
            self.assertFalse(any("PATCH" in command for command in runner.commands))

    def test_claim_output_failure_rolls_back(self):
        """Roll back a claim if its ownership output cannot be recorded."""
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "github-output"
            with (
                mock.patch.dict(self.mod.os.environ, {"GITHUB_OUTPUT": str(output)}),
                mock.patch.object(self.mod, "claim", return_value=7),
                mock.patch.object(self.mod, "record_release_id", side_effect=OSError("disk full")),
                mock.patch.object(self.mod, "cleanup") as cleanup,
            ):
                self.assertEqual(
                    1,
                    self.mod.main(
                        [
                            "claim",
                            "--repo",
                            "o/r",
                            "--tag",
                            "p-1",
                            "--commit",
                            "a" * 40,
                            "--name",
                            "p 1",
                            "--body",
                            "body",
                        ]
                    ),
                )
            cleanup.assert_called_once_with("o/r", 7, "p-1", "a" * 40)

    def test_cleanup_never_deletes_a_published_release(self):
        runner = FakeRunner([(0, {"id": 7, "draft": False, "tag_name": "p-1"})])
        self.mod.cleanup("o/r", 7, "p-1", "a" * 40, runner)
        self.assertEqual(len(runner.commands), 1)


if __name__ == "__main__":
    unittest.main()
