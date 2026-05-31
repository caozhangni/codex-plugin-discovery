import argparse
import pathlib
import sys
import unittest
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import list_recent_plugins


class ListRecentPluginsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)
        self.index = {
            "source": {"commit": "abc123"},
            "plugins": [
                {
                    "name": "old",
                    "display_name": "Old Plugin",
                    "category": "Productivity",
                    "plugin_path": "plugins/old",
                    "first_seen_at": "2026-05-20T12:00:00Z",
                    "first_seen_commit": "oldcommit",
                },
                {
                    "name": "newer",
                    "display_name": "Newer Plugin",
                    "category": "Research",
                    "plugin_path": "plugins/newer",
                    "first_seen_at": "2026-05-30T08:00:00Z",
                    "first_seen_commit": "newercommit",
                },
                {
                    "name": "newest",
                    "display_name": "Newest Plugin",
                    "category": "Design",
                    "plugin_path": "plugins/newest",
                    "first_seen_at": "2026-05-31T09:00:00Z",
                    "first_seen_commit": "newestcommit",
                },
            ],
        }

    def test_recent_plugins_are_filtered_sorted_and_limited(self):
        results = list_recent_plugins.recent_plugins(self.index, days=7, limit=2, now=self.now)

        self.assertEqual([plugin["name"] for plugin in results], ["newest", "newer"])

    def test_recent_plugins_include_boundary_day(self):
        results = list_recent_plugins.recent_plugins(
            {
                "plugins": [
                    {
                        "name": "boundary",
                        "first_seen_at": "2026-05-24T12:00:00Z",
                    },
                    {
                        "name": "too-old",
                        "first_seen_at": "2026-05-24T11:59:59Z",
                    },
                ]
            },
            days=7,
            limit=10,
            now=self.now,
        )

        self.assertEqual([plugin["name"] for plugin in results], ["boundary"])

    def test_render_results_mentions_scope_commit_and_first_seen_commit(self):
        rendered = list_recent_plugins.render_results(
            list_recent_plugins.recent_plugins(self.index, days=7, limit=10, now=self.now),
            self.index,
            days=7,
        )

        self.assertIn("Results only cover openai/plugins (commit: abc123)", rendered)
        self.assertIn("Newest Plugin (newest)", rendered)
        self.assertIn("First seen: 2026-05-31T09:00:00Z", rendered)
        self.assertIn("First seen commit: newestcommit", rendered)
        self.assertLess(rendered.index("Newest Plugin"), rendered.index("Newer Plugin"))
        self.assertNotIn("Old Plugin", rendered)

    def test_empty_result_suggests_wider_windows(self):
        rendered = list_recent_plugins.render_results([], {"source": {}}, days=9)

        self.assertIn("Results only cover openai/plugins", rendered)
        self.assertIn("No plugins were first added in the last 9 days.", rendered)
        self.assertIn("--days 14", rendered)
        self.assertIn("--days 30", rendered)

    def test_days_and_limit_must_be_positive(self):
        for value in ("0", "-1"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    list_recent_plugins.positive_int(value)

        self.assertEqual(list_recent_plugins.positive_int("3"), 3)

    def test_recent_plugins_rejects_non_positive_values(self):
        for kwargs in ({"days": 0, "limit": 1}, {"days": 1, "limit": 0}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    list_recent_plugins.recent_plugins(
                        self.index,
                        now=self.now,
                        **kwargs,
                    )


if __name__ == "__main__":
    unittest.main()
