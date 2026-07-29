#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "package_plugin.py"


def load_module():
    """
    Load and return the `package_plugin` module from the configured script path.
    
    Returns:
        module: The dynamically loaded `package_plugin` module.
    """
    spec = importlib.util.spec_from_file_location("package_plugin", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PackagePluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_tar_gz_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "plugin"
            binary.write_bytes(b"binary")
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            self.mod.build_tar_gz(binary, "plugin", first)
            self.mod.build_tar_gz(binary, "plugin", second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_zip_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "plugin.exe"
            binary.write_bytes(b"binary")
            first = root / "first.zip"
            second = root / "second.zip"
            self.mod.build_zip(binary, "plugin.exe", first)
            self.mod.build_zip(binary, "plugin.exe", second)
            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
