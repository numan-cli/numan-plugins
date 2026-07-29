#!/usr/bin/env python3
"""Enforce documentation coverage for PR #3's publication safety modules."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SAFETY_MODULES = (
    "ensure_release_absent.py",
    "gen_spec.py",
    "release_transaction.py",
    "validate_manifest.py",
)


class DocstringCoverageTests(unittest.TestCase):
    """Require module-level functions and classes to explain their contracts."""

    def test_publication_safety_modules_are_documented(self):
        """Report every missing module, function, or class docstring together."""
        missing: list[str] = []
        for filename in SAFETY_MODULES:
            tree = ast.parse((SCRIPTS / filename).read_text(encoding="utf-8"))
            if ast.get_docstring(tree) is None:
                missing.append(f"{filename}: module")
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if ast.get_docstring(node) is None:
                        missing.append(f"{filename}:{node.lineno}: {node.name}")
        self.assertEqual([], missing, "missing docstrings:\n" + "\n".join(missing))


if __name__ == "__main__":
    unittest.main()
