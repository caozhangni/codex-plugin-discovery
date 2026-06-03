import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_index
import search_index

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


def copy_fixture_to_git_repo(tmp_dir):
    repo_dir = pathlib.Path(tmp_dir) / "openai-plugins-sample"
    shutil.copytree(FIXTURE_REPO, repo_dir)
    run_git(repo_dir, "init")
    run_git(repo_dir, "config", "user.name", "Test User")
    run_git(repo_dir, "config", "user.email", "test@example.com")
    run_git(repo_dir, "add", ".")
    run_git(repo_dir, "commit", "-m", "Initial fixture")
    return repo_dir


class SearchIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = pathlib.Path(self.tmp.name) / "plugins-index.json"
        fixture_repo = copy_fixture_to_git_repo(self.tmp.name)
        build_index.build_index(fixture_repo, self.output, "abc123")

    def tearDown(self):
        self.tmp.cleanup()

    def test_search_returns_best_matching_plugin(self):
        index = search_index.load_index(self.output)
        results = search_index.search(index, "summarize support tickets", limit=2)

        self.assertEqual(results[0]["name"], "alpha")
        self.assertGreater(results[0]["score"], 0)
        self.assertIn("support", results[0]["matched_terms"])

    def test_search_output_mentions_scope_boundary(self):
        index = search_index.load_index(self.output)
        rendered = search_index.render_results(search_index.search(index, "dashboard charts", limit=1), index)

        self.assertIn("Beta Charts", rendered)
        self.assertIn("Results cover openai/plugins", rendered)
        self.assertIn("Indexed from: https://github.com/openai/plugins", rendered)

    def test_singular_query_matches_plural_metadata_terms(self):
        index = search_index.load_index(self.output)
        results = search_index.search(index, "chart", limit=1)

        self.assertEqual(results[0]["name"], "beta")
        self.assertIn("chart", results[0]["matched_terms"])
        self.assertIn("keywords", results[0]["matched_fields"])

    def test_short_stopword_queries_return_no_recommendations(self):
        index = search_index.load_index(self.output)

        for query in ("a", "to", "create a slide deck"):
            with self.subTest(query=query):
                self.assertEqual(search_index.search(index, query), [])

    def test_limit_must_be_positive(self):
        index = search_index.load_index(self.output)

        for limit in (0, -1):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    search_index.search(index, "support", limit=limit)

    def test_search_results_and_rendering_include_field_level_matches(self):
        index = {
            "source": {"commit": "abc123"},
            "plugins": [
                {
                    "name": "doc-helper",
                    "display_name": "Doc Helper",
                    "description": "Draft release notes",
                    "category": "Writing",
                    "keywords": ["release", "notes"],
                    "capabilities": ["summarization"],
                    "companion_surfaces": ["skills", "commands"],
                    "repository": "https://github.com/openai/plugins",
                    "source_repository": "https://github.com/openai/role-based-plugins",
                    "source_commit": "def456",
                    "search_text": "doc-helper doc helper draft release notes writing release notes summarization",
                }
            ],
        }

        results = search_index.search(index, "helper writing release summarization commands", limit=1)

        self.assertEqual(results[0]["matched_fields"]["name"], ["helper"])
        self.assertEqual(results[0]["matched_fields"]["display_name"], ["helper"])
        self.assertEqual(results[0]["matched_fields"]["description"], ["release"])
        self.assertEqual(results[0]["matched_fields"]["category"], ["writing"])
        self.assertEqual(results[0]["matched_fields"]["keywords"], ["release"])
        self.assertEqual(results[0]["matched_fields"]["capabilities"], ["summarization"])
        self.assertEqual(results[0]["matched_fields"]["companion_surfaces"], ["commands"])

        rendered = search_index.render_results(results, index)

        self.assertIn("Indexed from: https://github.com/openai/role-based-plugins", rendered)
        self.assertIn(
            "Matched fields: name (helper), display_name (helper), description (release), "
            "category (writing), keywords (release), capabilities (summarization), "
            "companion_surfaces (commands)",
            rendered,
        )
        self.assertNotIn("Matched fields: search_text", rendered)

    def test_search_no_match_mentions_both_source_repositories(self):
        index = {
            "sources": [
                {
                    "repository": "https://github.com/openai/plugins",
                    "commit": "abc123",
                    "scope": "plugins/*/.codex-plugin/plugin.json",
                },
                {
                    "repository": "https://github.com/openai/role-based-plugins",
                    "commit": "def456",
                    "scope": "plugins/*/.codex-plugin/plugin.json",
                },
            ],
            "plugins": [],
        }

        rendered = search_index.render_results([], index)

        self.assertIn("Results cover openai/plugins and openai/role-based-plugins", rendered)
        self.assertIn("No strong match was found in the indexed plugin sources.", rendered)
        self.assertIn("https://github.com/openai/plugins", rendered)
        self.assertIn("https://github.com/openai/role-based-plugins", rendered)


if __name__ == "__main__":
    unittest.main()
