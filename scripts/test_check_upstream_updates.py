import unittest
from unittest import mock
import urllib.request

from check_upstream_updates import (
    FetchError,
    _HttpOnlyRedirectHandler,
    _check_has_new_tag,
    _check_tag_moved,
    _determine_status,
    audit_entry,
    ensure_http_url,
    generate_markdown_report,
    http_opener,
    manifest_nu_upper_bound,
    nu_needs_bump,
    parse_version,
)


def make_entry(**overrides):
    entry = {
        "repo": "idanarye/nu_plugin_skim",
        "name": "nu_plugin_skim",
        "tag": "v0.29.1",
        "source_commit": "b86f26023a166492a0c2aea1e2c8cf803c29f813",
        "nu_version": ">=0.114.0 <0.115.0",
    }
    entry.update(overrides)
    return entry


class TestCheckUpstreamUpdates(unittest.TestCase):
    def test_ensure_http_url_valid(self):
        ensure_http_url("https://api.github.com/repos/owner/repo")
        ensure_http_url("http://example.com/api")

    def test_ensure_http_url_invalid_schemes(self):
        with self.assertRaises(ValueError):
            ensure_http_url("file:///etc/passwd")
        with self.assertRaises(ValueError):
            ensure_http_url("ftp://example.com/file")
        with self.assertRaises(ValueError):
            ensure_http_url("javascript:alert(1)")
        with self.assertRaises(ValueError):
            ensure_http_url(None)  # type: ignore

    def test_ensure_http_url_missing_host(self):
        with self.assertRaises(ValueError):
            ensure_http_url("https://")
        with self.assertRaises(ValueError):
            ensure_http_url("http://:8080")

    def test_http_redirect_handler_blocks_file_redirect(self):
        handler = _HttpOnlyRedirectHandler()
        req = urllib.request.Request("https://api.github.com/repos/owner/repo")
        with self.assertRaises(ValueError):
            handler.redirect_request(req, None, 302, "Found", {}, "file:///etc/passwd")

    def test_http_opener_constructs_opener(self):
        opener = http_opener()
        self.assertIsInstance(opener, urllib.request.OpenerDirector)

    def test_determine_status(self):
        self.assertEqual(_determine_status(True, False, False), "TAG_PROVENANCE_MISMATCH")
        self.assertEqual(_determine_status(False, True, True), "READY_FOR_BUMP")
        self.assertEqual(_determine_status(False, True, False), "UPSTREAM_NU_BUMP_NO_TAG")
        self.assertEqual(_determine_status(False, False, True), "NEW_TAG_AVAILABLE")
        self.assertEqual(_determine_status(False, False, False), "UP_TO_DATE")

    def test_generate_markdown_report(self):
        sample_results = [
            {
                "repo": "idanarye/nu_plugin_skim",
                "name": "nu_plugin_skim",
                "current_tag": "v0.29.1",
                "current_commit": "abcdef1",
                "current_nu": ">=0.114.0 <0.115.0",
                "latest_tags": ["v0.29.1"],
                "newest_tag": "v0.29.1",
                "cargo_nu_dep": "0.115",
                "has_new_tag": False,
                "status": "UPSTREAM_NU_BUMP_NO_TAG",
            }
        ]
        report = generate_markdown_report(sample_results)
        self.assertIn("# Upstream Plugin Audit Report", report)
        self.assertIn("nu_plugin_skim", report)
        self.assertIn("idanarye/nu_plugin_skim", report)
        self.assertIn("0.115", report)

    def test_parse_version_pads_components(self):
        self.assertEqual(parse_version("0.115"), (0, 115, 0))
        self.assertEqual(parse_version("0.115.1"), (0, 115, 1))
        self.assertEqual(parse_version("26.1140.0"), (26, 1140, 0))
        self.assertIsNone(parse_version("not-a-version"))

    def test_manifest_nu_upper_bound(self):
        self.assertEqual(
            manifest_nu_upper_bound(">=0.114.0 <0.115.0"), (0, 115, 0)
        )
        self.assertEqual(
            manifest_nu_upper_bound(">=0.90.0 <0.91.0"), (0, 91, 0)
        )
        self.assertEqual(manifest_nu_upper_bound("0.114.1"), (0, 114, 1))

    def test_nu_needs_bump(self):
        self.assertTrue(nu_needs_bump(">=0.114.0 <0.115.0", "0.115"))
        self.assertTrue(nu_needs_bump(">=0.114.0 <0.115.0", "0.116.0"))
        self.assertFalse(nu_needs_bump(">=0.114.0 <0.115.0", "0.114.1"))
        self.assertFalse(nu_needs_bump(">=0.114.0 <0.115.0", "garbage"))

    def test_fetch_error_fails_closed(self):
        entry = make_entry()
        with mock.patch(
            "check_upstream_updates.fetch_latest_tags",
            side_effect=FetchError("rate limited"),
        ):
            result = audit_entry(entry)
        self.assertEqual(result["status"], "FETCH_ERROR")
        self.assertIn("rate limited", result["error"])

    def test_tag_provenance_mismatch_flagged(self):
        entry = make_entry()
        with mock.patch("check_upstream_updates.fetch_latest_tags") as tags, mock.patch(
            "check_upstream_updates.fetch_cargo_toml_nu_dep"
        ) as cargo, mock.patch(
            "check_upstream_updates.resolve_tag_commit"
        ) as resolve:
            tags.return_value = [{"name": "v0.29.1", "commit_sha": "0" * 40}]
            cargo.return_value = "0.114.1"
            resolve.return_value = "f" * 40
            result = audit_entry(entry)
        self.assertEqual(result["status"], "TAG_PROVENANCE_MISMATCH")

    def test_tag_missing_upstream_flagged(self):
        entry = make_entry()
        with mock.patch("check_upstream_updates.fetch_latest_tags") as tags, mock.patch(
            "check_upstream_updates.fetch_cargo_toml_nu_dep"
        ) as cargo, mock.patch(
            "check_upstream_updates.resolve_tag_commit"
        ) as resolve:
            tags.return_value = [{"name": "v0.29.1", "commit_sha": "0" * 40}]
            cargo.return_value = "0.114.1"
            resolve.return_value = None
            result = audit_entry(entry)
        self.assertEqual(result["status"], "TAG_PROVENANCE_MISMATCH")

    def test_tagged_up_to_date(self):
        entry = make_entry()
        with mock.patch("check_upstream_updates.fetch_latest_tags") as tags, mock.patch(
            "check_upstream_updates.fetch_cargo_toml_nu_dep"
        ) as cargo, mock.patch(
            "check_upstream_updates.resolve_tag_commit"
        ) as resolve:
            tags.return_value = [{"name": "v0.29.1", "commit_sha": "0" * 40}]
            cargo.return_value = "0.114"
            resolve.return_value = entry["source_commit"]
            result = audit_entry(entry)
        self.assertEqual(result["status"], "UP_TO_DATE")
        self.assertFalse(result["has_new_tag"])

    def test_new_tag_available(self):
        entry = make_entry()
        with mock.patch("check_upstream_updates.fetch_latest_tags") as tags, mock.patch(
            "check_upstream_updates.fetch_cargo_toml_nu_dep"
        ) as cargo, mock.patch(
            "check_upstream_updates.resolve_tag_commit"
        ) as resolve:
            tags.return_value = [{"name": "v0.30.0", "commit_sha": "0" * 40}]
            cargo.return_value = "0.114"
            resolve.return_value = entry["source_commit"]
            result = audit_entry(entry)
        self.assertEqual(result["status"], "NEW_TAG_AVAILABLE")
        self.assertTrue(result["has_new_tag"])

    def test_nu_bump_with_new_tag_ready_for_bump(self):
        entry = make_entry()
        with mock.patch("check_upstream_updates.fetch_latest_tags") as tags, mock.patch(
            "check_upstream_updates.fetch_cargo_toml_nu_dep"
        ) as cargo, mock.patch(
            "check_upstream_updates.resolve_tag_commit"
        ) as resolve:
            tags.return_value = [{"name": "v0.30.0", "commit_sha": "0" * 40}]
            cargo.return_value = "0.116"
            resolve.return_value = entry["source_commit"]
            result = audit_entry(entry)
        self.assertEqual(result["status"], "READY_FOR_BUMP")

    def test_nu_bump_without_new_tag(self):
        entry = make_entry()
        with mock.patch("check_upstream_updates.fetch_latest_tags") as tags, mock.patch(
            "check_upstream_updates.fetch_cargo_toml_nu_dep"
        ) as cargo, mock.patch(
            "check_upstream_updates.resolve_tag_commit"
        ) as resolve:
            tags.return_value = [{"name": "v0.29.1", "commit_sha": "0" * 40}]
            cargo.return_value = "0.116"
            resolve.return_value = entry["source_commit"]
            result = audit_entry(entry)
        self.assertEqual(result["status"], "UPSTREAM_NU_BUMP_NO_TAG")

    def test_snapshot_with_newer_tag_flagged(self):
        entry = make_entry(
            tag=None,
            intake_mode="commit-snapshot",
            source_commit="5a1ca2a5ceba60108a4ca6d45ec18d213abb5227",
        )
        with mock.patch("check_upstream_updates.fetch_latest_tags") as tags, mock.patch(
            "check_upstream_updates.fetch_cargo_toml_nu_dep"
        ) as cargo, mock.patch(
            "check_upstream_updates.resolve_tag_commit"
        ) as resolve:
            tags.return_value = [{"name": "v0.104.0", "commit_sha": "0" * 40}]
            cargo.return_value = "0.105"
            resolve.return_value = "f" * 40
            result = audit_entry(entry)
        self.assertEqual(result["status"], "NEW_TAG_AVAILABLE")

    def test_snapshot_at_newest_tag_up_to_date(self):
        entry = make_entry(
            tag=None,
            intake_mode="commit-snapshot",
            source_commit="5a1ca2a5ceba60108a4ca6d45ec18d213abb5227",
        )
        with mock.patch("check_upstream_updates.fetch_latest_tags") as tags, mock.patch(
            "check_upstream_updates.fetch_cargo_toml_nu_dep"
        ) as cargo, mock.patch(
            "check_upstream_updates.resolve_tag_commit"
        ) as resolve:
            tags.return_value = [{"name": "v0.104.0", "commit_sha": "0" * 40}]
            cargo.return_value = "0.104"
            resolve.return_value = entry["source_commit"]
            result = audit_entry(entry)
        self.assertEqual(result["status"], "UP_TO_DATE")

    def test_fetch_error_reported_in_markdown(self):
        results = [
            {
                "repo": "owner/repo",
                "name": "nu_plugin_x",
                "current_tag": None,
                "current_commit": "",
                "current_nu": "",
                "latest_tags": [],
                "newest_tag": None,
                "cargo_nu_dep": "unknown",
                "has_new_tag": False,
                "error": "HTTP 403 from https://api.github.com/...",
                "status": "FETCH_ERROR",
            }
        ]
        report = generate_markdown_report(results)
        self.assertIn("FETCH_ERROR", report)
        self.assertIn("HTTP 403", report)


if __name__ == "__main__":
    unittest.main()
