# Recent Plugin Discovery Design

## Goal

Add support for questions like "Have any Codex plugins been added recently?" and "What plugins were added in the last few days?"

The feature answers from upstream `openai/plugins` git history only. It does not inspect local Codex plugin caches, does not compare local index snapshots, does not cover the full Codex App Plugin Directory, and does not install plugins.

## Scope

"Recently added" means a direct plugin manifest path first appeared in the upstream repository:

```text
plugins/*/.codex-plugin/plugin.json
```

The first commit that adds that manifest is treated as the plugin's first-seen time. Nested fixture manifests remain out of scope.

If the user asks "recently" or "the last few days" without a number, the skill uses a 7 day default window.

The first version stays simple:

- No `--skip-history` option
- No local index diff mode
- No fallback index without history fields
- No automatic plugin installation
- No combined time-plus-keyword filtering

If git history collection fails while building the index, the build should fail rather than write an index that cannot answer recent-plugin questions correctly.

## Index Changes

`build_index.py` will add two fields to every plugin record:

```json
{
  "first_seen_at": "2026-05-29T10:12:34+00:00",
  "first_seen_commit": "abc123..."
}
```

The timestamp uses git's strict ISO 8601 committer date format from `%cI`.

The simplest implementation is to run one git history query per direct manifest path:

```bash
git log --diff-filter=A --format=%H%x00%cI -- plugins/foo/.codex-plugin/plugin.json
```

The oldest returned commit is the first-seen commit. This prioritizes clarity over batch optimization. The repository cache should contain enough history for this query to work reliably.

## Query Script

Add a new script:

```text
skills/codex-plugin-discovery/scripts/list_recent_plugins.py
```

The script:

- Reads `index/plugins-index.json` by default
- Accepts `--days`, defaulting to `7`
- Accepts `--limit`, defaulting to `10`
- Filters plugins with `first_seen_at` within the requested window
- Sorts matches by `first_seen_at` descending
- Renders Markdown-ish output consistent with `search_index.py`

Example output:

```text
Results only cover openai/plugins (commit: abc123)

Plugins first added in the last 7 day(s):

1. Some Plugin (some-plugin)
   Added: 2026-05-29
   Category: Developer Tools
   What it does: Example description.
   Source: plugins/some-plugin
   First seen commit: abc123
```

If no plugins match:

```text
Results only cover openai/plugins (commit: abc123)

No plugins were first added in the last 7 day(s).
Try a wider window, such as --days 14 or --days 30.
```

## Skill Workflow

Update `SKILL.md` so the skill routes recent-plugin questions to `list_recent_plugins.py`.

Recent-plugin queries use the same on-demand freshness behavior as recommendation
queries. When the user invokes the skill, the agent checks whether
`index/plugins-index.json` is missing or stale before answering. `stale` means the
stored upstream commit SHA differs from `git ls-remote https://github.com/openai/plugins HEAD`.
If the index is missing or stale, the agent runs `python3 scripts/build_index.py`
first, then runs `list_recent_plugins.py`.

Trigger examples include:

- "Have any plugins been added recently?"
- "What new Codex plugins appeared in the last week?"
- "最近几天有什么新增的插件吗？"
- "过去 30 天新增了哪些插件？"

If the user gives an explicit day count, pass that count to `--days`. If the user does not provide a count, use 7 days.

For mixed questions like "What recently added plugin can help with spreadsheets?", the first version should keep behavior simple: answer recent additions by time and suggest a separate task search if the user wants recommendations for a capability.

## README Updates

Update the usage section with a recent-plugin example:

```text
Have any Codex plugins been added recently?
```

Update the index-generation note to explain that the builder reads upstream git history to record when direct plugin manifests first appeared.

## Tests

Extend `test_build_index.py` with a temporary git repository created during the test:

1. Create `plugins/alpha/.codex-plugin/plugin.json` and commit it.
2. Create `plugins/beta/.codex-plugin/plugin.json` and commit it.
3. Build the index from that repo.
4. Assert each plugin has `first_seen_at` and `first_seen_commit`.
5. Assert alpha and beta have distinct first-seen commits.

Keep the existing fixture tests for direct manifest scanning and nested fixture exclusion.

Add `test_list_recent_plugins.py` covering:

- Default 7 day window
- Explicit `--days`
- Descending sort by `first_seen_at`
- Empty result rendering
- Scope boundary text mentioning `openai/plugins`
- Positive integer validation for `--days` and `--limit`

## Acceptance Criteria

- The generated index records first-seen git metadata for every direct plugin manifest.
- After the on-demand freshness check has completed, `list_recent_plugins.py` answers from the generated index without making its own network call.
- "Recently" defaults to 7 days.
- Results remain explicitly scoped to `openai/plugins`.
- Existing recommendation search behavior continues to work.
