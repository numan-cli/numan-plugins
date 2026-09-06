#!/usr/bin/env python3
"""Unit checks for the non-binary archive intake lane."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent / "intake_archive.py"
SHA = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"


def load_intake_archive():
    spec = importlib.util.spec_from_file_location("intake_archive", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class RecordingRunner:
    """Fake subprocess runner: records each argv and replays canned results."""

    def __init__(self, results=()):
        self.results = list(results)
        self.calls: list[list[str]] = []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        returncode, stdout, stderr = self.results.pop(0) if self.results else (1, "", "boom")
        return subprocess.CompletedProcess(list(args), returncode, stdout, stderr)

    @property
    def refs(self) -> list[str]:
        """Return the ref candidate of every recorded `git ls-remote` call."""
        return [call[3] for call in self.calls if call[1] == "ls-remote"]


class IntakeArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ia = load_intake_archive()

    def _tree(self, root: Path) -> None:
        (root / "nested").mkdir(parents=True)
        (root / "mod.nu").write_text("export def hi [] { }\n", encoding="utf-8")
        (root / "nested" / "extra.nu").write_text("# extra\n", encoding="utf-8")
        (root / ".git").mkdir()
        (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    def test_normalize_git_url_expands_owner_name_slug(self):
        self.assertEqual(
            self.ia.normalize_git_url("owner/repo"), "https://github.com/owner/repo"
        )

    def test_normalize_git_url_leaves_full_url_alone(self):
        for url in (
            "https://github.com/owner/repo",
            "git://example.invalid/repo.git",
            "ssh://git@example.invalid/repo.git",
            "git@github.com:owner/repo.git",
        ):
            self.assertEqual(self.ia.normalize_git_url(url), url)

    def test_validate_git_url_rejects_option_like_url(self):
        with self.assertRaisesRegex(ValueError, "may not start with"):
            self.ia.validate_git_url("--upload-pack=evil")

    def test_validate_git_url_rejects_unsupported_scheme(self):
        with self.assertRaisesRegex(ValueError, "must use https"):
            self.ia.validate_git_url("file:///tmp/repo")

    def test_validate_git_url_accepts_supported_schemes(self):
        self.ia.validate_git_url("https://github.com/owner/repo")
        self.ia.validate_git_url("git@github.com:owner/repo.git")

    def test_validate_identifier_rejects_empty_and_path_like_values(self):
        for value in ("", " ", "..", "../escape", "owner/name", "-flag"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "--name must match"):
                    self.ia.validate_identifier("--name", value)

    def test_validate_identifier_accepts_registry_and_version_shapes(self):
        self.ia.validate_identifier("--owner", "nushell")
        self.ia.validate_identifier("--name", "cool_module.nu-2")
        self.ia.validate_identifier("--version", "0.1.0-abc1234", self.ia.VERSION_RE)
        self.ia.validate_identifier("--version", "1.2.3+build.5", self.ia.VERSION_RE)

    def test_resolve_ref_returns_annotated_tag_sha(self):
        runner = RecordingRunner([(0, f"{SHA}\trefs/tags/v1.0.0^{{}}\n", "")])
        resolved = self.ia.resolve_ref(
            "https://github.com/owner/repo", "v1.0.0", runner=runner
        )
        self.assertEqual(resolved, SHA)
        self.assertEqual(runner.refs, ["refs/tags/v1.0.0^{}"])

    def test_resolve_ref_falls_through_to_branch(self):
        runner = RecordingRunner(
            [(1, "", ""), (0, "", ""), (0, f"{SHA}\trefs/heads/main\n", "")]
        )
        resolved = self.ia.resolve_ref("https://github.com/owner/repo", "main", runner=runner)
        self.assertEqual(resolved, SHA)
        self.assertEqual(
            runner.refs, ["refs/tags/main^{}", "refs/tags/main", "refs/heads/main"]
        )

    def test_resolve_ref_rejects_ambiguous_match(self):
        runner = RecordingRunner(
            [(0, f"{SHA}\trefs/tags/x\n{'b' * 40}\trefs/tags/x-suffix\n", "")]
        )
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.ia.resolve_ref("https://github.com/owner/repo", "x", runner=runner)

    def test_resolve_ref_accepts_full_sha_when_unadvertised(self):
        runner = RecordingRunner()
        self.assertEqual(
            self.ia.resolve_ref("https://github.com/owner/repo", SHA, runner=runner), SHA
        )

    def test_resolve_ref_rejects_unresolvable_ref(self):
        runner = RecordingRunner()
        with self.assertRaisesRegex(ValueError, "could not resolve"):
            self.ia.resolve_ref("https://github.com/owner/repo", "nope", runner=runner)

    def test_resolve_ref_tries_candidates_in_order(self):
        runner = RecordingRunner()
        with self.assertRaises(ValueError):
            self.ia.resolve_ref("https://github.com/owner/repo", "topic", runner=runner)
        self.assertEqual(
            runner.refs,
            ["refs/tags/topic^{}", "refs/tags/topic", "refs/heads/topic", "topic"],
        )

    def test_shallow_clone_at_runs_init_fetch_checkout(self):
        runner = RecordingRunner([(0, "", "")] * 4)
        self.ia.shallow_clone_at(
            "https://github.com/owner/repo", SHA, Path("src"), runner=runner
        )
        self.assertEqual([call[1] for call in runner.calls], ["init", "-C", "-C", "-C"])
        self.assertIn("fetch", runner.calls[2])
        self.assertIn("--depth", runner.calls[2])
        self.assertEqual(runner.calls[3][-1], SHA)

    def test_shallow_clone_at_raises_with_git_stderr(self):
        runner = RecordingRunner([(0, "", ""), (0, "", ""), (128, "", "bad object")])
        with self.assertRaisesRegex(ValueError, "bad object"):
            self.ia.shallow_clone_at(
                "https://github.com/owner/repo", SHA, Path("src"), runner=runner
            )

    def test_verify_entry_accepts_nested_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            self.assertEqual(
                self.ia.verify_entry(root, "nested/extra.nu"),
                (root / "nested" / "extra.nu").resolve(),
            )

    def test_verify_entry_rejects_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            with self.assertRaisesRegex(ValueError, "must be relative"):
                self.ia.verify_entry(root, str(root / "mod.nu"))

    def test_verify_entry_rejects_escaping_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "src"
            root.mkdir()
            (Path(tmp) / "outside.nu").write_text("# outside\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escapes checkout"):
                self.ia.verify_entry(root, "../outside.nu")

    def test_verify_entry_rejects_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            with self.assertRaisesRegex(ValueError, "not found in checkout"):
                self.ia.verify_entry(root, "missing.nu")

    def test_sorted_files_skips_git_and_sorts_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            (root / "aaa.nu").write_text("# a\n", encoding="utf-8")
            self.assertEqual(
                [rel.as_posix() for rel in self.ia.sorted_files(root)],
                ["aaa.nu", "mod.nu", "nested/extra.nu"],
            )

    def test_sorted_files_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._tree(root)
            try:
                (root / "link.nu").symlink_to(root / "mod.nu")
            except OSError:
                self.skipTest("symlink creation not permitted on this host")
            with self.assertRaisesRegex(ValueError, "symlink not allowed"):
                self.ia.sorted_files(root)

    def test_build_archive_is_byte_identical_across_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            self._tree(src)
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            self.ia.build_archive(src, first)
            self.ia.build_archive(src, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_build_archive_zeroes_the_gzip_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            self._tree(src)
            out = root / "out.tar.gz"
            self.ia.build_archive(src, out)
            self.assertEqual(out.read_bytes()[4:8], b"\x00\x00\x00\x00")

    def test_build_archive_normalizes_member_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            self._tree(src)
            out = root / "out.tar.gz"
            self.ia.build_archive(src, out)
            with tarfile.open(out, "r:gz") as tar:
                members = tar.getmembers()
            self.assertEqual(
                [member.name for member in members],
                ["mod.nu", "nested/extra.nu"],
            )
            for member in members:
                self.assertEqual(member.mtime, self.ia.FIXED_MTIME)
                self.assertEqual((member.uid, member.gid), (0, 0))
                self.assertEqual((member.uname, member.gname), ("", ""))

    def test_build_archive_normalizes_member_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            src.mkdir()
            (src / "plain.nu").write_text("# plain\n", encoding="utf-8")
            runnable = src / "run.nu"
            runnable.write_text("# run\n", encoding="utf-8")
            os.chmod(runnable, 0o755)
            if not runnable.stat().st_mode & 0o111:
                self.skipTest("host filesystem does not record the exec bit")
            out = root / "out.tar.gz"
            self.ia.build_archive(src, out)
            with tarfile.open(out, "r:gz") as tar:
                modes = {member.name: member.mode for member in tar.getmembers()}
            self.assertEqual(modes, {"plain.nu": 0o644, "run.nu": 0o755})

    def test_build_archive_leaves_no_partial_archive_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            self._tree(src)
            dist = root / "dist"
            dist.mkdir()
            with mock.patch.object(
                self.ia.tarfile, "open", side_effect=OSError("no space left on device")
            ):
                with self.assertRaisesRegex(OSError, "no space left"):
                    self.ia.build_archive(src, dist / "out.tar.gz")
            self.assertEqual(list(dist.iterdir()), [])

    def test_build_archive_rejects_too_many_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            self._tree(src)
            with mock.patch.object(self.ia, "MAX_ARCHIVE_FILES", 1):
                with self.assertRaisesRegex(ValueError, "exceeds the archive limit of 1"):
                    self.ia.build_archive(src, root / "out.tar.gz")

    def test_build_archive_rejects_oversized_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            self._tree(src)
            with mock.patch.object(self.ia, "MAX_ARCHIVE_BYTES", 4):
                with self.assertRaisesRegex(ValueError, "bytes exceeds the archive limit of 4"):
                    self.ia.build_archive(src, root / "out.tar.gz")

    def test_derive_version_uses_semver_shaped_ref(self):
        self.assertEqual(self.ia.derive_version("v1.2.3", SHA), "1.2.3")
        self.assertEqual(self.ia.derive_version("1.2.3", SHA), "1.2.3")
        self.assertEqual(self.ia.derive_version("v1.2.3-rc.1", SHA), "1.2.3-rc.1")

    def test_derive_version_falls_back_to_short_sha(self):
        self.assertEqual(self.ia.derive_version("main", SHA), f"0.1.0-{SHA[:7]}")

    def test_release_tag_and_archive_filename_shapes(self):
        self.assertEqual(
            self.ia.release_tag("owner", "cool-module", "1.2.3"),
            "archive-owner-cool-module-1.2.3",
        )
        self.assertEqual(
            self.ia.archive_filename("owner", "cool-module", "1.2.3"),
            "owner-cool-module-1.2.3.tar.gz",
        )

    def _spec_kwargs(self, **overrides):
        kwargs = {
            "owner": "owner",
            "name": "cool-module",
            "description": "A cool module.",
            "git_url": "https://github.com/owner/repo",
            "pkg_type": "module",
            "tags": ["module"],
            "version": "1.2.3",
            "nu_version": ">=0.114.0 <0.115.0",
            "entry": "cool.nu",
            "url": "https://example.invalid/download/archive-owner-cool-module-1.2.3/owner-cool-module-1.2.3.tar.gz",
            "sha256": "c" * 64,
        }
        kwargs.update(overrides)
        return kwargs

    def test_build_spec_emits_archive_artifact_with_inline_sha256(self):
        spec = self.ia.build_spec(**self._spec_kwargs())
        self.assertEqual(
            spec["artifact"],
            {
                "kind": "archive",
                "url": self._spec_kwargs()["url"],
                "entry": "cool.nu",
                "sha256": "c" * 64,
            },
        )
        self.assertNotIn("verified_with", spec)
        self.assertNotIn("source", spec)
        self.assertEqual(spec["repo"], "https://github.com/owner/repo")

    def test_build_spec_omits_activation_without_kind(self):
        spec = self.ia.build_spec(**self._spec_kwargs(activation_import="all"))
        self.assertNotIn("activation", spec)

    def test_build_spec_emits_activation_when_kind_given(self):
        spec = self.ia.build_spec(
            **self._spec_kwargs(activation_kind="nu-module", activation_import="all")
        )
        self.assertEqual(spec["activation"], {"kind": "nu-module", "import": "all"})

    def test_build_spec_provisional_emits_stripped_evidence_tier(self):
        spec = self.ia.build_spec(
            **self._spec_kwargs(provisional=True, deferral_reason="  needs a Nu 0.114 host\n")
        )
        self.assertEqual(spec["evidence_tier"], "provisional")
        self.assertEqual(spec["deferral_reason"], "needs a Nu 0.114 host")
        self.assertNotIn("verified_with", spec)
        keys = list(spec)
        self.assertEqual(
            keys[keys.index("nu_version") + 1 : keys.index("artifact")],
            ["evidence_tier", "deferral_reason"],
        )

    def test_build_spec_non_provisional_omits_evidence_keys(self):
        spec = self.ia.build_spec(**self._spec_kwargs())
        self.assertNotIn("evidence_tier", spec)
        self.assertNotIn("deferral_reason", spec)

    def _activation_kwargs(self, **overrides):
        kwargs = {
            "entry": "cool.nu",
            "activation_kind": None,
            "activation_import": None,
            "provisional": False,
            "deferral_reason": None,
        }
        kwargs.update(overrides)
        return kwargs

    def test_validate_activation_requires_provisional(self):
        with self.assertRaisesRegex(ValueError, "requires provisional intake"):
            self.ia.validate_activation(
                **self._activation_kwargs(activation_kind="nu-module")
            )

    def test_validate_activation_requires_deferral_reason(self):
        with self.assertRaisesRegex(ValueError, "deferral reason"):
            self.ia.validate_activation(**self._activation_kwargs(provisional=True))

    def test_validate_activation_rejects_blank_deferral_reason(self):
        with self.assertRaisesRegex(ValueError, "deferral reason"):
            self.ia.validate_activation(
                **self._activation_kwargs(provisional=True, deferral_reason="  \t\n")
            )

    def test_validate_activation_rejects_reason_without_provisional(self):
        with self.assertRaisesRegex(ValueError, "only recorded for provisional"):
            self.ia.validate_activation(
                **self._activation_kwargs(deferral_reason="needs a Nu host")
            )

    def test_validate_activation_rejects_mod_nu_with_module_import(self):
        with self.assertRaisesRegex(ValueError, "requires activation import 'all'"):
            self.ia.validate_activation(
                **self._activation_kwargs(
                    entry="mod.nu",
                    activation_kind="nu-module",
                    activation_import="module",
                    provisional=True,
                    deferral_reason="needs a Nu host",
                )
            )

    def test_validate_activation_rejects_mod_nu_with_default_import(self):
        with self.assertRaisesRegex(ValueError, "requires activation import 'all'"):
            self.ia.validate_activation(
                **self._activation_kwargs(
                    entry="pkg/mod.nu",
                    activation_kind="nu-module",
                    provisional=True,
                    deferral_reason="needs a Nu host",
                )
            )

    def test_validate_activation_allows_mod_nu_with_import_all(self):
        self.ia.validate_activation(
            **self._activation_kwargs(
                entry="mod.nu",
                activation_kind="nu-module",
                activation_import="all",
                provisional=True,
                deferral_reason="needs a Nu host",
            )
        )

    def test_validate_activation_allows_named_entry_with_module_import(self):
        self.ia.validate_activation(
            **self._activation_kwargs(
                entry="foo.nu",
                activation_kind="nu-module",
                activation_import="module",
                provisional=True,
                deferral_reason="needs a Nu host",
            )
        )

    def test_parse_tags_accepts_json_array_of_strings(self):
        self.assertEqual(self.ia.parse_tags('["module", "nu"]'), ["module", "nu"])

    def test_parse_tags_rejects_non_array(self):
        with self.assertRaisesRegex(ValueError, "JSON array of strings"):
            self.ia.parse_tags('{"tags": []}')

    def test_parse_tags_rejects_non_string_members(self):
        with self.assertRaisesRegex(ValueError, "JSON array of strings"):
            self.ia.parse_tags("[1, 2]")

    def _record(self, path: Path, **overrides):
        kwargs = {
            "git_url": "https://github.com/owner/repo",
            "ref": "v1.2.3",
            "resolved_sha": SHA,
            "entry": "cool.nu",
            "name": "cool-module",
            "owner": "owner",
            "pkg_type": "module",
        }
        kwargs.update(overrides)
        self.ia.record_archive_manifest(path, **kwargs)

    def test_record_archive_manifest_creates_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest-archives.json"
            self._record(path)
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            self.assertEqual(
                json.loads(text),
                [
                    {
                        "git": "https://github.com/owner/repo",
                        "ref": "v1.2.3",
                        "resolved_sha": SHA,
                        "entry": "cool.nu",
                        "name": "cool-module",
                        "owner": "owner",
                        "type": "module",
                    }
                ],
            )

    def test_record_archive_manifest_upserts_and_sorts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest-archives.json"
            self._record(path, owner="zowner", name="zed")
            self._record(path)
            self._record(path, ref="v2.0.0", resolved_sha="b" * 40)
            entries = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                [(entry["owner"], entry["name"]) for entry in entries],
                [("owner", "cool-module"), ("zowner", "zed")],
            )
            self.assertEqual(entries[0]["ref"], "v2.0.0")
            self.assertEqual(entries[0]["resolved_sha"], "b" * 40)

    def test_record_archive_manifest_rejects_non_array_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest-archives.json"
            path.write_text('{"owner": "owner"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON array of objects"):
                self._record(path)

    def test_record_archive_manifest_rejects_non_object_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest-archives.json"
            path.write_text('["owner/cool-module"]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON array of objects"):
                self._record(path)

    def _main_argv(self, root: Path, *extra: str) -> list[str]:
        return [
            "--git-url", "https://github.com/owner/repo",
            "--ref", "v1.2.3",
            "--entry", "mod.nu",
            "--owner", "owner",
            "--name", "cool-module",
            "--type", "module",
            "--description", "A cool module.",
            "--tags", '["module"]',
            "--nu-version", ">=0.114.0 <0.115.0",
            "--release-root", "https://example.invalid/releases/download/",
            "--archive-out", str(root / "dist"),
            "--out", str(root / "spec.json"),
            "--manifest-archives", str(root / "manifest-archives.json"),
            *extra,
        ]

    def _clone_stub(self, tree=True):
        def stub(git_url, sha, dest, runner=None):
            dest.mkdir(parents=True, exist_ok=True)
            if tree:
                self._tree(dest)
        return stub

    @contextlib.contextmanager
    def _patched_network(self, clone_stub):
        stdout = io.StringIO()
        with mock.patch.object(self.ia, "resolve_ref", return_value=SHA), mock.patch.object(
            self.ia, "shallow_clone_at", clone_stub
        ), contextlib.redirect_stdout(stdout):
            yield stdout

    def test_main_writes_archive_spec_and_manifest_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self._patched_network(self._clone_stub()) as stdout:
                rc = self.ia.main(self._main_argv(root))
            self.assertEqual(rc, 0)
            archive = root / "dist" / "owner-cool-module-1.2.3.tar.gz"
            self.assertTrue(archive.is_file())
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            spec = json.loads((root / "spec.json").read_text(encoding="utf-8"))
            self.assertEqual(
                spec["artifact"],
                {
                    "kind": "archive",
                    "url": (
                        "https://example.invalid/releases/download/"
                        "archive-owner-cool-module-1.2.3/owner-cool-module-1.2.3.tar.gz"
                    ),
                    "entry": "mod.nu",
                    "sha256": digest,
                },
            )
            self.assertEqual(spec["version"], "1.2.3")
            records = json.loads((root / "manifest-archives.json").read_text(encoding="utf-8"))
            self.assertEqual(records[0]["resolved_sha"], SHA)
            self.assertEqual(records[0]["ref"], "v1.2.3")
            self.assertIn(
                "ARCHIVED\t"
                f"{SHA}\t1.2.3\tarchive-owner-cool-module-1.2.3\t"
                f"owner-cool-module-1.2.3.tar.gz\t{digest}",
                stdout.getvalue(),
            )

    def test_main_provisional_spec_carries_evidence_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            argv = self._main_argv(
                root, "--provisional", "--deferral-reason", "needs a Nu 0.114 host"
            )
            with self._patched_network(self._clone_stub()):
                rc = self.ia.main(argv)
            self.assertEqual(rc, 0)
            spec = json.loads((root / "spec.json").read_text(encoding="utf-8"))
            self.assertEqual(spec["evidence_tier"], "provisional")
            self.assertEqual(spec["deferral_reason"], "needs a Nu 0.114 host")
            self.assertNotIn("verified_with", spec)

    def test_main_missing_entry_writes_neither_spec_nor_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            argv = self._main_argv(root)
            argv[argv.index("--entry") + 1] = "missing.nu"
            with self._patched_network(self._clone_stub()):
                rc = self.ia.main(argv)
            self.assertEqual(rc, 1)
            self.assertFalse((root / "spec.json").exists())
            self.assertFalse((root / "manifest-archives.json").exists())
            self.assertEqual(list((root / "dist").iterdir()), [])

    def test_main_accepts_a_repo_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            argv = self._main_argv(root)
            argv[argv.index("--git-url")] = "--repo"
            argv[argv.index("--repo") + 1] = "owner/repo"
            with self._patched_network(self._clone_stub()):
                rc = self.ia.main(argv)
            self.assertEqual(rc, 0)
            spec = json.loads((root / "spec.json").read_text(encoding="utf-8"))
            self.assertEqual(spec["repo"], "https://github.com/owner/repo")

    def test_main_requires_a_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            argv = self._main_argv(root)
            index = argv.index("--git-url")
            del argv[index : index + 2]
            with self._patched_network(self._clone_stub()):
                rc = self.ia.main(argv)
            self.assertEqual(rc, 1)
            self.assertFalse((root / "spec.json").exists())

    def test_main_rejects_a_path_like_package_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            argv = self._main_argv(root)
            argv[argv.index("--name") + 1] = "../escape"
            with self._patched_network(self._clone_stub()):
                rc = self.ia.main(argv)
            self.assertEqual(rc, 1)
            self.assertFalse((root / "spec.json").exists())
            self.assertFalse((root / "dist").exists())

    def test_main_refuses_to_overwrite_an_existing_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dist").mkdir()
            archive = root / "dist" / "owner-cool-module-1.2.3.tar.gz"
            archive.write_bytes(b"published already")
            with self._patched_network(self._clone_stub()):
                rc = self.ia.main(self._main_argv(root))
            self.assertEqual(rc, 1)
            self.assertEqual(archive.read_bytes(), b"published already")
            self.assertFalse((root / "spec.json").exists())


if __name__ == "__main__":
    unittest.main()
