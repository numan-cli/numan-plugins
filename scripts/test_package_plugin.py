#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

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

    def test_is_windows_target(self):
        self.assertTrue(self.mod.is_windows_target("x86_64-pc-windows-msvc"))
        self.assertFalse(self.mod.is_windows_target("x86_64-unknown-linux-gnu"))

    def test_executable_name(self):
        self.assertEqual(
            self.mod.executable_name("plugin", "x86_64-pc-windows-msvc"), "plugin.exe"
        )
        self.assertEqual(
            self.mod.executable_name("plugin", "x86_64-unknown-linux-gnu"), "plugin"
        )

    def test_main_missing_binary_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            argv = [
                "package_plugin.py",
                "--binary", str(root / "missing"),
                "--name", "plugin",
                "--version", "1.0.0",
                "--target", "x86_64-unknown-linux-gnu",
                "--outdir", str(root / "dist"),
            ]
            with mock.patch.object(sys, "argv", argv):
                rc = self.mod.main()
            self.assertEqual(rc, 1)

    def test_main_writes_tar_gz_and_prints_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "plugin"
            binary.write_bytes(b"binary")
            outdir = root / "nested" / "dist"
            argv = [
                "package_plugin.py",
                "--binary", str(binary),
                "--name", "plugin",
                "--version", "1.0.0",
                "--target", "x86_64-unknown-linux-gnu",
                "--outdir", str(outdir),
            ]
            buf = io.StringIO()
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
                rc = self.mod.main()
            self.assertEqual(rc, 0)
            expected = outdir / "plugin-1.0.0-x86_64-unknown-linux-gnu.tar.gz"
            self.assertTrue(expected.is_file())
            digest = self.mod.hashlib.sha256(expected.read_bytes()).hexdigest()
            record = buf.getvalue().strip()
            self.assertIn(expected.name, record)
            self.assertIn(digest, record)

    def test_main_refuses_to_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "plugin"
            binary.write_bytes(b"binary")
            outdir = root / "dist"
            outdir.mkdir()
            existing = outdir / "plugin-1.0.0-x86_64-unknown-linux-gnu.tar.gz"
            existing.write_bytes(b"pre-existing content")
            argv = [
                "package_plugin.py",
                "--binary", str(binary),
                "--name", "plugin",
                "--version", "1.0.0",
                "--target", "x86_64-unknown-linux-gnu",
                "--outdir", str(outdir),
            ]
            with mock.patch.object(sys, "argv", argv):
                rc = self.mod.main()
            self.assertEqual(rc, 1)
            self.assertEqual(existing.read_bytes(), b"pre-existing content")

    def test_main_writes_zip_for_windows_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "plugin.exe"
            binary.write_bytes(b"binary")
            outdir = root / "dist"
            argv = [
                "package_plugin.py",
                "--binary", str(binary),
                "--name", "plugin",
                "--version", "1.0.0",
                "--target", "x86_64-pc-windows-msvc",
                "--outdir", str(outdir),
            ]
            with mock.patch.object(sys, "argv", argv):
                rc = self.mod.main()
            self.assertEqual(rc, 0)
            archive = outdir / "plugin-1.0.0-x86_64-pc-windows-msvc.zip"
            self.assertTrue(archive.is_file())
            with zipfile.ZipFile(archive) as zf:
                self.assertEqual(zf.namelist(), ["plugin.exe"])
                self.assertEqual(zf.read("plugin.exe"), b"binary")


if __name__ == "__main__":
    unittest.main()
