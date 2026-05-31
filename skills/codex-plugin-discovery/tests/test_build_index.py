import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_index


FIXTURE_REPO = ROOT / "tests" / "fixtures" / "openai-plugins-sample"


def run_git(repo_dir, *args, env=None):
    result = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    return result.stdout.strip()


def init_git_repo(repo_dir):
    repo_dir.mkdir(parents=True, exist_ok=True)
    run_git(repo_dir, "init")
    run_git(repo_dir, "config", "user.name", "Test User")
    run_git(repo_dir, "config", "user.email", "test@example.com")
    return repo_dir


def commit_all(repo_dir, message, date):
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
    }
    run_git(repo_dir, "add", ".")
    run_git(repo_dir, "commit", "-m", message, env=env)
    return run_git(repo_dir, "rev-parse", "HEAD")


def write_manifest(repo_dir, plugin_name):
    manifest_path = repo_dir / "plugins" / plugin_name / ".codex-plugin" / "plugin.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"name": plugin_name, "description": f"{plugin_name} plugin"}),
        encoding="utf-8",
    )
    return manifest_path


def copy_fixture_to_git_repo(tmp_dir):
    repo_dir = pathlib.Path(tmp_dir) / "openai-plugins-sample"
    shutil.copytree(FIXTURE_REPO, repo_dir)
    init_git_repo(repo_dir)
    commit_all(repo_dir, "Initial fixture", "2026-05-01T12:00:00+00:00")
    return repo_dir


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
            repo_dir = copy_fixture_to_git_repo(tmp_dir)

            index = build_index.build_index(
                repo_dir=repo_dir,
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

    def test_build_index_records_manifest_first_seen_metadata(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = init_git_repo(pathlib.Path(tmp_dir) / "repo")
            output = pathlib.Path(tmp_dir) / "plugins-index.json"

            write_manifest(repo_dir, "alpha")
            alpha_commit = commit_all(
                repo_dir,
                "Add alpha plugin",
                "2026-05-01T12:00:00+00:00",
            )
            write_manifest(repo_dir, "beta")
            beta_commit = commit_all(
                repo_dir,
                "Add beta plugin",
                "2026-05-02T12:00:00+00:00",
            )

            index = build_index.build_index(
                repo_dir=repo_dir,
                output_path=output,
                upstream_sha="abc123",
            )

            plugins = {plugin["name"]: plugin for plugin in index["plugins"]}
            self.assertIn("first_seen_commit", plugins["alpha"])
            self.assertIn("first_seen_at", plugins["alpha"])
            self.assertIn("first_seen_commit", plugins["beta"])
            self.assertIn("first_seen_at", plugins["beta"])
            self.assertEqual(plugins["alpha"]["first_seen_commit"], alpha_commit)
            self.assertEqual(plugins["alpha"]["first_seen_at"], "2026-05-01T12:00:00Z")
            self.assertEqual(plugins["beta"]["first_seen_commit"], beta_commit)
            self.assertEqual(plugins["beta"]["first_seen_at"], "2026-05-02T12:00:00Z")
            self.assertNotEqual(
                plugins["alpha"]["first_seen_commit"],
                plugins["beta"]["first_seen_commit"],
            )

    def test_manifest_first_seen_reports_path_when_git_log_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = pathlib.Path(tmp_dir) / "not-git"
            manifest_path = write_manifest(repo_dir, "alpha")

            with self.assertRaisesRegex(
                ValueError,
                "Failed to read first-seen history for plugins/alpha/.codex-plugin/plugin.json",
            ) as raised:
                build_index.manifest_first_seen(manifest_path, repo_dir)

            self.assertIn("fatal:", str(raised.exception))

    def test_main_with_repo_dir_does_not_call_remote_head(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = pathlib.Path(tmp_dir) / "plugins-index.json"
            repo_dir = copy_fixture_to_git_repo(tmp_dir)
            original_remote_head = build_index.remote_head
            original_argv = sys.argv

            def fail_if_called():
                raise AssertionError("remote_head should not be called when --repo-dir is provided")

            try:
                build_index.remote_head = fail_if_called
                sys.argv = [
                    "build_index.py",
                    "--repo-dir",
                    str(repo_dir),
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
