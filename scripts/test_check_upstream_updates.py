import unittest
from check_upstream_updates import generate_markdown_report


class TestCheckUpstreamUpdates(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
