# Recent Plugin Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add recent-plugin discovery by recording when each direct `openai/plugins` manifest first appeared and listing plugins added within a recent time window.

**Architecture:** Extend index building to include first-seen git metadata for each direct plugin manifest. Add a focused `list_recent_plugins.py` script that reads the generated index, filters by `first_seen_at`, and renders results. Update the skill instructions, README, and plugin mirror so users are routed through the new behavior.

**Tech Stack:** Python 3 standard library, `unittest`, git CLI, Markdown skill/README docs.

---

## File Structure

- Modify `skills/codex-plugin-discovery/scripts/build_index.py`: remove shallow clone behavior and add first-seen git metadata to each plugin record.
- Create `skills/codex-plugin-discovery/scripts/list_recent_plugins.py`: list recently added plugins from `plugins-index.json`.
- Modify `skills/codex-plugin-discovery/tests/test_build_index.py`: add temporary git repo coverage for first-seen metadata.
- Create `skills/codex-plugin-discovery/tests/test_list_recent_plugins.py`: cover recent listing, sorting, empty output, and argument validation helpers.
- Modify `skills/codex-plugin-discovery/SKILL.md`: route recent/new plugin questions to the new script and preserve on-demand freshness checks.
- Modify `README.md`: document recent-plugin usage and history-aware index generation.
- Mirror all changed skill files into `plugins/codex-plugin-discovery/skills/codex-plugin-discovery/...` after source skill tests pass.

## Task 1: Build Index First-Seen Metadata

**Files:**
- Modify: `skills/codex-plugin-discovery/scripts/build_index.py`
- Test: `skills/codex-plugin-discovery/tests/test_build_index.py`

- [ ] **Step 1: Write the failing first-seen metadata test**

Add imports and helpers to `skills/codex-plugin-discovery/tests/test_build_index.py`:

```python
import os
import subprocess
```

```python
def run_git(args, cwd, env=None):
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    return result.stdout.strip()


def write_manifest(repo, plugin_name, display_name):
    manifest_dir = repo / "plugins" / plugin_name / ".codex-plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps(
            {
                "name": plugin_name,
                "description": f"{display_name} description",
                "interface": {
                    "displayName": display_name,
                    "category": "Testing",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
```

Add this test method:

```python
    def test_build_index_records_manifest_first_seen_git_metadata(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = pathlib.Path(tmp_dir) / "repo"
            repo.mkdir()
            run_git(["init"], cwd=repo)
            run_git(["config", "user.name", "Test User"], cwd=repo)
            run_git(["config", "user.email", "test@example.com"], cwd=repo)

            env = os.environ.copy()
            env.update(
                {
                    "GIT_AUTHOR_DATE": "2026-05-01T12:00:00+00:00",
                    "GIT_COMMITTER_DATE": "2026-05-01T12:00:00+00:00",
                }
            )
            write_manifest(repo, "alpha", "Alpha Support")
            run_git(["add", "plugins/alpha/.codex-plugin/plugin.json"], cwd=repo)
            run_git(["commit", "-m", "Add alpha"], cwd=repo, env=env)
            alpha_commit = run_git(["rev-parse", "HEAD"], cwd=repo)

            env.update(
                {
                    "GIT_AUTHOR_DATE": "2026-05-02T12:00:00+00:00",
                    "GIT_COMMITTER_DATE": "2026-05-02T12:00:00+00:00",
                }
            )
            write_manifest(repo, "beta", "Beta Charts")
            run_git(["add", "plugins/beta/.codex-plugin/plugin.json"], cwd=repo)
            run_git(["commit", "-m", "Add beta"], cwd=repo, env=env)
            beta_commit = run_git(["rev-parse", "HEAD"], cwd=repo)

            output = pathlib.Path(tmp_dir) / "plugins-index.json"
            index = build_index.build_index(repo_dir=repo, output_path=output, upstream_sha=beta_commit)

            plugins = {plugin["name"]: plugin for plugin in index["plugins"]}
            self.assertEqual(plugins["alpha"]["first_seen_commit"], alpha_commit)
            self.assertEqual(plugins["alpha"]["first_seen_at"], "2026-05-01T12:00:00+00:00")
            self.assertEqual(plugins["beta"]["first_seen_commit"], beta_commit)
            self.assertEqual(plugins["beta"]["first_seen_at"], "2026-05-02T12:00:00+00:00")
            self.assertNotEqual(plugins["alpha"]["first_seen_commit"], plugins["beta"]["first_seen_commit"])
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest skills/codex-plugin-discovery/tests/test_build_index.py -v
```

Expected: FAIL because `first_seen_commit` and `first_seen_at` are not present.

- [ ] **Step 3: Implement full-history repo fetching and first-seen lookup**

In `skills/codex-plugin-discovery/scripts/build_index.py`, update `ensure_repo()`:

```python
def ensure_repo(cache_dir: Path) -> Path:
    """Ensure the upstream plugin repository is cached and checked out with history."""
    repo_dir = cache_dir / "openai-plugins"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not repo_dir.exists():
        run_git(["clone", REPOSITORY_URL, str(repo_dir)])
    else:
        run_git(["fetch", "origin", "HEAD"], cwd=repo_dir)
        run_git(["checkout", "--detach", "FETCH_HEAD"], cwd=repo_dir)

    return repo_dir
```

Add the first-seen helper:

```python
def manifest_first_seen(manifest_path: Path, repo_dir: Path) -> dict[str, str]:
    """Return the commit and timestamp where a manifest first appeared."""
    rel_path = manifest_path.relative_to(repo_dir).as_posix()
    output = run_git(
        [
            "log",
            "--diff-filter=A",
            "--format=%H%x00%cI",
            "--",
            rel_path,
        ],
        cwd=repo_dir,
    )
    entries = [line for line in output.splitlines() if line.strip()]
    if not entries:
        raise ValueError(f"No first-seen git history found for {rel_path}")

    commit, timestamp = entries[-1].split("\x00", 1)
    return {
        "first_seen_commit": commit,
        "first_seen_at": timestamp,
    }
```

Update `build_plugin_record()` to include the metadata:

```python
    first_seen = manifest_first_seen(manifest_path, repo_dir)

    return {
        "name": name,
        "display_name": display_name,
        "description": description,
        "category": category,
        "keywords": keywords,
        "capabilities": capabilities,
        "repository": repository,
        "homepage": homepage,
        "plugin_path": plugin_path,
        "manifest_path": manifest_rel_path,
        "first_seen_at": first_seen["first_seen_at"],
        "first_seen_commit": first_seen["first_seen_commit"],
        "companion_surfaces": surfaces,
        "search_text": " ".join(part for part in search_parts if part).lower(),
    }
```

- [ ] **Step 4: Run build index tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest skills/codex-plugin-discovery/tests/test_build_index.py -v
```

Expected: existing non-git fixture tests fail because the static fixture has no git history.

- [ ] **Step 5: Convert existing fixture-based tests to temporary git repos**

In `test_build_index.py`, add:

```python
def copy_fixture_to_git_repo(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE_REPO, repo)
    run_git(["init"], cwd=repo)
    run_git(["config", "user.name", "Test User"], cwd=repo)
    run_git(["config", "user.email", "test@example.com"], cwd=repo)
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_DATE": "2026-05-01T12:00:00+00:00",
            "GIT_COMMITTER_DATE": "2026-05-01T12:00:00+00:00",
        }
    )
    run_git(["add", "."], cwd=repo)
    run_git(["commit", "-m", "Add fixture plugins"], cwd=repo, env=env)
    return repo
```

Also import:

```python
import shutil
```

For tests that call `build_index.build_index(FIXTURE_REPO, ...)`, wrap them in a temp dir and pass `copy_fixture_to_git_repo(pathlib.Path(tmp_dir))` instead. Keep `test_scan_direct_plugin_manifests_excludes_nested_fixtures` using `FIXTURE_REPO`, because scanning does not need git history.

- [ ] **Step 6: Run build index tests until green**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest skills/codex-plugin-discovery/tests/test_build_index.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add skills/codex-plugin-discovery/scripts/build_index.py skills/codex-plugin-discovery/tests/test_build_index.py
git commit -m "Add plugin first-seen metadata to index"
```

## Task 2: Recent Plugin Listing Script

**Files:**
- Create: `skills/codex-plugin-discovery/scripts/list_recent_plugins.py`
- Create: `skills/codex-plugin-discovery/tests/test_list_recent_plugins.py`

- [ ] **Step 1: Write tests for recent listing behavior**

Create `skills/codex-plugin-discovery/tests/test_list_recent_plugins.py`:

```python
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import list_recent_plugins


class ListRecentPluginsTests(unittest.TestCase):
    def index(self):
        return {
            "source": {
                "repository": "https://github.com/openai/plugins",
                "commit": "abc123",
                "scope": "plugins/*/.codex-plugin/plugin.json",
            },
            "plugins": [
                {
                    "name": "old-plugin",
                    "display_name": "Old Plugin",
                    "description": "Older helper",
                    "category": "Developer Tools",
                    "plugin_path": "plugins/old-plugin",
                    "first_seen_at": "2026-05-01T12:00:00+00:00",
                    "first_seen_commit": "old123",
                },
                {
                    "name": "newer-plugin",
                    "display_name": "Newer Plugin",
                    "description": "Newest helper",
                    "category": "Productivity",
                    "plugin_path": "plugins/newer-plugin",
                    "first_seen_at": "2026-05-30T12:00:00+00:00",
                    "first_seen_commit": "newer123",
                },
                {
                    "name": "new-plugin",
                    "display_name": "New Plugin",
                    "description": "Recent helper",
                    "category": "",
                    "plugin_path": "plugins/new-plugin",
                    "first_seen_at": "2026-05-29T12:00:00+00:00",
                    "first_seen_commit": "new123",
                },
            ],
        }

    def test_recent_plugins_defaults_to_seven_days_and_sorts_descending(self):
        now = list_recent_plugins.parse_datetime("2026-05-31T12:00:00+00:00")
        results = list_recent_plugins.recent_plugins(self.index(), now=now)

        self.assertEqual([plugin["name"] for plugin in results], ["newer-plugin", "new-plugin"])

    def test_recent_plugins_accepts_explicit_days_and_limit(self):
        now = list_recent_plugins.parse_datetime("2026-05-31T12:00:00+00:00")
        results = list_recent_plugins.recent_plugins(self.index(), days=40, limit=2, now=now)

        self.assertEqual([plugin["name"] for plugin in results], ["newer-plugin", "new-plugin"])

    def test_render_results_mentions_scope_boundary(self):
        now = list_recent_plugins.parse_datetime("2026-05-31T12:00:00+00:00")
        results = list_recent_plugins.recent_plugins(self.index(), now=now)
        rendered = list_recent_plugins.render_results(results, self.index(), days=7)

        self.assertIn("Results only cover openai/plugins (commit: abc123)", rendered)
        self.assertIn("Plugins first added in the last 7 day(s):", rendered)
        self.assertIn("Newer Plugin (newer-plugin)", rendered)
        self.assertIn("Added: 2026-05-30", rendered)
        self.assertIn("Category: Uncategorized", rendered)
        self.assertIn("First seen commit: new123", rendered)

    def test_render_empty_results(self):
        rendered = list_recent_plugins.render_results([], self.index(), days=3)

        self.assertIn("No plugins were first added in the last 3 day(s).", rendered)
        self.assertIn("Try a wider window, such as --days 14 or --days 30.", rendered)

    def test_positive_int_validation(self):
        self.assertEqual(list_recent_plugins.positive_int("7"), 7)
        for value in ("0", "-1"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "must be a positive integer"):
                    list_recent_plugins.positive_int(value)

    def test_load_index_reads_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = pathlib.Path(tmp_dir) / "plugins-index.json"
            path.write_text('{"plugins": []}', encoding="utf-8")

            self.assertEqual(list_recent_plugins.load_index(path), {"plugins": []})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest skills/codex-plugin-discovery/tests/test_list_recent_plugins.py -v
```

Expected: FAIL because `list_recent_plugins.py` does not exist.

- [ ] **Step 3: Implement `list_recent_plugins.py`**

Create `skills/codex-plugin-discovery/scripts/list_recent_plugins.py`:

```python
#!/usr/bin/env python3
"""List Codex plugins recently added to the generated index."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_DAYS = 7
DEFAULT_LIMIT = 10


def load_index(path: Path) -> dict[str, Any]:
    """Read a plugin index from JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def parse_datetime(value: str) -> datetime:
    """Parse an ISO 8601 timestamp from the index."""
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def positive_int(value: str) -> int:
    """Parse a positive integer argument."""
    parsed = int(value)
    if parsed < 1:
        raise ValueError("must be a positive integer")
    return parsed


def argparse_positive_int(value: str) -> int:
    """Argparse wrapper for positive integer arguments."""
    try:
        return positive_int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def recent_plugins(
    index: dict[str, Any],
    days: int = DEFAULT_DAYS,
    limit: int = DEFAULT_LIMIT,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return plugins first seen within the requested window."""
    if days < 1:
        raise ValueError("days must be a positive integer")
    if limit < 1:
        raise ValueError("limit must be a positive integer")

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    cutoff = current_time - timedelta(days=days)

    results = []
    for plugin in index.get("plugins", []):
        first_seen_at = plugin.get("first_seen_at")
        if not first_seen_at:
            raise ValueError(f"Missing first_seen_at for plugin {plugin.get('name') or 'unknown'}")
        first_seen = parse_datetime(str(first_seen_at))
        if first_seen >= cutoff:
            result = dict(plugin)
            result["_first_seen_datetime"] = first_seen
            results.append(result)

    results.sort(key=lambda plugin: plugin["_first_seen_datetime"], reverse=True)
    for plugin in results:
        plugin.pop("_first_seen_datetime", None)
    return results[:limit]


def render_results(results: list[dict[str, Any]], index: dict[str, Any], days: int) -> str:
    """Render recent plugins as Markdown-ish output."""
    source = index.get("source") or {}
    commit = source.get("commit")
    first_line = "Results only cover openai/plugins"
    if commit:
        first_line = f"{first_line} (commit: {commit})"

    lines = [first_line, ""]
    if not results:
        lines.append(f"No plugins were first added in the last {days} day(s).")
        lines.append("Try a wider window, such as --days 14 or --days 30.")
        return "\n".join(lines)

    lines.append(f"Plugins first added in the last {days} day(s):")
    lines.append("")
    for position, plugin in enumerate(results, start=1):
        display_name = plugin.get("display_name") or plugin.get("name") or "Unknown plugin"
        name = plugin.get("name") or display_name
        category = plugin.get("category") or "Uncategorized"
        description = plugin.get("description") or "No description provided."
        source_location = plugin.get("repository") or plugin.get("homepage") or plugin.get("plugin_path") or ""
        first_seen_at = parse_datetime(str(plugin.get("first_seen_at"))).date().isoformat()
        first_seen_commit = plugin.get("first_seen_commit") or "unknown"

        lines.append(f"{position}. {display_name} ({name})")
        lines.append(f"   Added: {first_seen_at}")
        lines.append(f"   Category: {category}")
        lines.append(f"   What it does: {description}")
        lines.append(f"   Source: {source_location}")
        lines.append(f"   First seen commit: {first_seen_commit}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=Path("index/plugins-index.json"))
    parser.add_argument("--days", type=argparse_positive_int, default=DEFAULT_DAYS)
    parser.add_argument("--limit", type=argparse_positive_int, default=DEFAULT_LIMIT)
    args = parser.parse_args()

    index = load_index(args.index)
    print(render_results(recent_plugins(index, days=args.days, limit=args.limit), index, days=args.days))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run recent listing tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest skills/codex-plugin-discovery/tests/test_list_recent_plugins.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add skills/codex-plugin-discovery/scripts/list_recent_plugins.py skills/codex-plugin-discovery/tests/test_list_recent_plugins.py
git commit -m "Add recent plugin listing script"
```

## Task 3: Skill and README Routing

**Files:**
- Modify: `skills/codex-plugin-discovery/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Update skill workflow**

In `skills/codex-plugin-discovery/SKILL.md`, replace the `## Workflow` list with:

```markdown
## Workflow

1. If the user asks what plugins are currently enabled/installed in this session, answer from the current session's available plugin list first. Keep it concise.
2. If the user asks broadly what plugins are available, can be used, or exist in the marketplace, do not list every indexed plugin. State that this skill can search `openai/plugins`, explain the coverage limit, and ask for the task or category they care about.
3. If the user asks about recently added, new, last-week, past-N-days, or "最近几天" plugins, use the recent-plugin workflow:
   - If `index/plugins-index.json` is missing or stale, run `python3 scripts/build_index.py`.
   - Use `python3 scripts/list_recent_plugins.py`.
   - If the user provides a day count, pass it as `--days N`; otherwise use the script default of 7 days.
   - Do not combine recency filtering with task recommendation in this first version. For mixed requests, answer recent additions and offer to run a separate task search.
4. If the user asks for discoverable, installable, marketplace, or task-relevant plugins, use this skill's index.
5. If `index/plugins-index.json` is missing or stale, run `python3 scripts/build_index.py`.
6. Search with a concrete query, such as `python3 scripts/search_index.py "summarize support tickets"`.
7. Present up to five candidates from the index.
8. Explain matched fields and why each plugin may help.
9. State that results only cover plugins present in `openai/plugins`.
```

- [ ] **Step 2: Update output shape with recent results**

Add this section after the broad availability output shape:

```markdown
For recent-plugin questions, include:

- Plugin name and display name
- Added date
- Category
- Description
- Repository or plugin path
- First-seen commit
- A clear note that results only cover `openai/plugins`

If no plugin was added in the requested window, say so and suggest a wider window such as 14 or 30 days.
```

- [ ] **Step 3: Update README usage examples**

In `README.md`, add this example after the specific-plugin example:

````markdown
Ask what was added recently:

```text
Have any Codex plugins been added recently?
```
````

- [ ] **Step 4: Update README index note**

In `README.md`, change the index regeneration introduction to:

```markdown
Regenerate it with the builder. The builder fetches `openai/plugins` and reads git history so each direct plugin manifest records when it first appeared:
```

- [ ] **Step 5: Verify docs contain the new route**

Run:

```bash
rg -n "recent|recently|最近|list_recent_plugins|first appeared" README.md skills/codex-plugin-discovery/SKILL.md
```

Expected: output includes README recent example, `list_recent_plugins.py`, stale check wording, and history-aware index generation wording.

- [ ] **Step 6: Commit Task 3**

```bash
git add README.md skills/codex-plugin-discovery/SKILL.md
git commit -m "Document recent plugin discovery workflow"
```

## Task 4: Mirror Skill Into Plugin Package

**Files:**
- Modify: `plugins/codex-plugin-discovery/skills/codex-plugin-discovery/SKILL.md`
- Modify: `plugins/codex-plugin-discovery/skills/codex-plugin-discovery/scripts/build_index.py`
- Create: `plugins/codex-plugin-discovery/skills/codex-plugin-discovery/scripts/list_recent_plugins.py`
- Modify: `plugins/codex-plugin-discovery/skills/codex-plugin-discovery/tests/test_build_index.py`
- Create: `plugins/codex-plugin-discovery/skills/codex-plugin-discovery/tests/test_list_recent_plugins.py`

- [ ] **Step 1: Copy source skill changes into the plugin mirror**

Run:

```bash
cp skills/codex-plugin-discovery/SKILL.md plugins/codex-plugin-discovery/skills/codex-plugin-discovery/SKILL.md
cp skills/codex-plugin-discovery/scripts/build_index.py plugins/codex-plugin-discovery/skills/codex-plugin-discovery/scripts/build_index.py
cp skills/codex-plugin-discovery/scripts/list_recent_plugins.py plugins/codex-plugin-discovery/skills/codex-plugin-discovery/scripts/list_recent_plugins.py
cp skills/codex-plugin-discovery/tests/test_build_index.py plugins/codex-plugin-discovery/skills/codex-plugin-discovery/tests/test_build_index.py
cp skills/codex-plugin-discovery/tests/test_list_recent_plugins.py plugins/codex-plugin-discovery/skills/codex-plugin-discovery/tests/test_list_recent_plugins.py
```

- [ ] **Step 2: Verify mirror files match source files**

Run:

```bash
diff -u skills/codex-plugin-discovery/SKILL.md plugins/codex-plugin-discovery/skills/codex-plugin-discovery/SKILL.md
diff -u skills/codex-plugin-discovery/scripts/build_index.py plugins/codex-plugin-discovery/skills/codex-plugin-discovery/scripts/build_index.py
diff -u skills/codex-plugin-discovery/scripts/list_recent_plugins.py plugins/codex-plugin-discovery/skills/codex-plugin-discovery/scripts/list_recent_plugins.py
diff -u skills/codex-plugin-discovery/tests/test_build_index.py plugins/codex-plugin-discovery/skills/codex-plugin-discovery/tests/test_build_index.py
diff -u skills/codex-plugin-discovery/tests/test_list_recent_plugins.py plugins/codex-plugin-discovery/skills/codex-plugin-discovery/tests/test_list_recent_plugins.py
```

Expected: each `diff` command exits with no output.

- [ ] **Step 3: Run plugin mirror tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s plugins/codex-plugin-discovery/skills/codex-plugin-discovery/tests -v
```

Expected: PASS.

- [ ] **Step 4: Commit Task 4**

```bash
git add plugins/codex-plugin-discovery/skills/codex-plugin-discovery
git commit -m "Mirror recent plugin discovery into plugin package"
```

## Task 5: Regenerate Index and Verify Package

**Files:**
- Modify: `skills/codex-plugin-discovery/index/plugins-index.json`
- Modify: `plugins/codex-plugin-discovery/skills/codex-plugin-discovery/index/plugins-index.json`

- [ ] **Step 1: Regenerate the source skill index**

Run:

```bash
cd skills/codex-plugin-discovery
python3 scripts/build_index.py --cache-dir .cache --output index/plugins-index.json
rm -rf .cache
```

Expected: output like `indexed 148 plugins from <sha>`. The exact count may differ if upstream changed.

- [ ] **Step 2: Verify generated index contains first-seen fields**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
index = json.loads(Path("skills/codex-plugin-discovery/index/plugins-index.json").read_text())
missing = [p["name"] for p in index["plugins"] if not p.get("first_seen_at") or not p.get("first_seen_commit")]
print("plugins", len(index["plugins"]))
print("missing", missing[:5])
raise SystemExit(1 if missing else 0)
PY
```

Expected: prints plugin count and `missing []`.

- [ ] **Step 3: Run recent listing against the regenerated index**

Run:

```bash
cd skills/codex-plugin-discovery
python3 scripts/list_recent_plugins.py --days 30 --limit 5
```

Expected: prints the `Results only cover openai/plugins` boundary and either up to five recent plugins or the no-results message.

- [ ] **Step 4: Copy regenerated index to plugin mirror**

Run:

```bash
cp skills/codex-plugin-discovery/index/plugins-index.json plugins/codex-plugin-discovery/skills/codex-plugin-discovery/index/plugins-index.json
```

- [ ] **Step 5: Run full test suite and validators**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s skills/codex-plugin-discovery/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s plugins/codex-plugin-discovery/skills/codex-plugin-discovery/tests -v
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/codex-plugin-discovery
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/codex-plugin-discovery
```

Expected: all commands pass.

- [ ] **Step 6: Inspect final diff**

Run:

```bash
git status --short
git diff --stat
git diff -- README.md skills/codex-plugin-discovery/SKILL.md skills/codex-plugin-discovery/scripts/build_index.py skills/codex-plugin-discovery/scripts/list_recent_plugins.py
```

Expected: only recent-plugin discovery changes are present.

- [ ] **Step 7: Commit Task 5**

```bash
git add skills/codex-plugin-discovery/index/plugins-index.json plugins/codex-plugin-discovery/skills/codex-plugin-discovery/index/plugins-index.json
git commit -m "Regenerate plugin index with first-seen metadata"
```

## Self-Review

- Spec coverage: Tasks cover index metadata, recent listing script, 7 day default, output boundary, skill routing, README updates, tests, plugin mirror, and generated index verification.
- Scope control: The plan does not add local snapshot diffing, auto-installation, combined recency-plus-keyword filtering, skip-history flags, or CI automation.
- Type consistency: `first_seen_at` and `first_seen_commit` are the only new index fields. `recent_plugins(index, days=7, limit=10, now=None)` is used consistently by tests and CLI.
- Test posture: Tests are written before implementation in each code task, and fixture history is created in temporary git repos so tests do not depend on upstream network state.
