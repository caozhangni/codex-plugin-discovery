import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_index


FIXTURE_REPO = ROOT / "tests" / "fixtures" / "openai-plugins-sample"


class BuildIndexTests(unittest.TestCase):
    def test_scan_direct_plugin_manifests_excludes_nested_fixtures(self):
        manifests = build_index.scan_manifest_paths(FIXTURE_REPO)
        rel_paths = [str(path.relative_to(FIXTURE_REPO)) for path in manifests]

        self.assertEqual(
            rel_paths,
            [
                "plugins/alpha/.codex-plugin/plugin.json",
                "plugins/beta/.codex-plugin/plugin.json",
            ],
        )

    def test_build_index_extracts_recommendation_fields(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = pathlib.Path(tmp_dir) / "plugins-index.json"

            index = build_index.build_index(
                repo_dir=FIXTURE_REPO,
                output_path=output,
                upstream_sha="abc123",
            )

            self.assertTrue(output.exists())
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(written, index)
            self.assertEqual(index["source"]["repository"], "https://github.com/openai/plugins")
            self.assertEqual(index["source"]["commit"], "abc123")
            self.assertEqual([plugin["name"] for plugin in index["plugins"]], ["alpha", "beta"])
            self.assertNotIn("fixture-plugin", output.read_text(encoding="utf-8"))
            self.assertNotIn("Fixture Plugin", output.read_text(encoding="utf-8"))

            alpha = index["plugins"][0]
            self.assertEqual(alpha["display_name"], "Alpha Support")
            self.assertEqual(alpha["category"], "Productivity")
            self.assertIn("analyze customer support tickets", alpha["search_text"])
            self.assertIn("support", alpha["keywords"])
            self.assertIn("summarization", alpha["capabilities"])

            beta = index["plugins"][1]
            self.assertEqual(beta["display_name"], "Beta Charts")
            self.assertEqual(beta["category"], "Data")
            self.assertIn("dashboard", beta["keywords"])
            self.assertIn("charts", beta["capabilities"])
            self.assertIn("analytics dashboards", beta["search_text"])

    def test_main_with_repo_dir_does_not_call_remote_head(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = pathlib.Path(tmp_dir) / "plugins-index.json"
            original_remote_head = build_index.remote_head
            original_argv = sys.argv

            def fail_if_called():
                raise AssertionError("remote_head should not be called when --repo-dir is provided")

            try:
                build_index.remote_head = fail_if_called
                sys.argv = [
                    "build_index.py",
                    "--repo-dir",
                    str(FIXTURE_REPO),
                    "--output",
                    str(output),
                ]
                build_index.main()
            finally:
                build_index.remote_head = original_remote_head
                sys.argv = original_argv

            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(written["source"]["commit"], "local")
            self.assertEqual([plugin["name"] for plugin in written["plugins"]], ["alpha", "beta"])

    def test_build_index_rejects_repo_without_direct_manifests(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            empty_repo = pathlib.Path(tmp_dir) / "empty-repo"
            empty_repo.mkdir()
            output = pathlib.Path(tmp_dir) / "plugins-index.json"

            with self.assertRaisesRegex(ValueError, "No direct plugin manifests found"):
                build_index.build_index(
                    repo_dir=empty_repo,
                    output_path=output,
                    upstream_sha="abc123",
                )

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
