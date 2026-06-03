---
name: codex-plugin-discovery
description: Use when a user asks what Codex plugins are available or can be used, wants plugin recommendations for a task, asks to find/search/discover installable plugins, asks about the plugin marketplace, or asks whether a plugin can help with a task.
---

# Codex Plugin Discovery

Discover candidate Codex plugins from the official `openai/plugins` and `openai/role-based-plugins` GitHub repositories.

## Core Rule

Use only metadata indexed from:

```text
https://github.com/openai/plugins
https://github.com/openai/role-based-plugins
```

This boundary is intentional, even under deadline or coverage pressure. Do not read Codex `.tmp` marketplace caches, installed plugin caches, or active-session tool caches. Those sources are out of scope.

Do not auto-install plugins. Recommend candidates and explain the evidence only. Do not claim this covers the full Codex App Plugin Directory.

## Workflow

1. If the user asks what plugins are currently enabled/installed in this session, answer from the current session's available plugin list first. Keep it concise.
2. If the user asks broadly what plugins are available, can be used, or exist in the marketplace, do not list every indexed plugin. State that this skill can search `openai/plugins` and `openai/role-based-plugins`, explain the coverage limit, and ask for the task or category they care about.
3. If the user asks for recent, recently added, new, last-week, past-N-days, or 最近几天 plugins, route to `python3 scripts/list_recent_plugins.py`. If the user provides a day count, pass `--days N`; otherwise use the default 7-day window. If `index/plugins-index.json` is missing or stale, run `python3 scripts/build_index.py` first. For mixed requests that ask for both recency and task recommendation, do not combine recency filtering with task recommendation in this first version; answer recent additions first and offer a separate task search.
4. If the user asks for discoverable, installable, marketplace, or task-relevant plugins, use this skill's index.
5. If `index/plugins-index.json` is missing or stale, run `python3 scripts/build_index.py`.
6. Search with a concrete query, such as `python3 scripts/search_index.py "summarize support tickets"`.
7. Present up to five candidates from the index.
8. Explain matched fields and why each plugin may help.
9. State that results only cover plugins present in `openai/plugins` and `openai/role-based-plugins`.

`stale` means any stored source commit differs from `git ls-remote <source repository> HEAD` for either configured repository.

## Index Boundary

Index only direct plugin manifests:

```text
plugins/*/.codex-plugin/plugin.json
```

Do not recursively include nested manifests such as `plugins/plugin-eval/fixtures/...`; valid fixture JSON is still test data, not a recommendable plugin.

## Output Shape

For broad availability questions such as "what plugins can I use?", do not dump the full index. Answer with:

- The current-session plugin list if the user asked about enabled plugins
- A short note that discoverable candidates can be searched from `openai/plugins` and `openai/role-based-plugins`
- A request for the task, domain, or category to search
- At most five examples or categories if examples would help

For each recommendation, include:

- Plugin name and display name
- Category
- Why it matches
- Matched fields
- Repository or plugin path
- Confidence note

For recent-plugin results, include:

- Plugin name and display name
- Added date
- Category
- Description
- Repository or plugin path
- First-seen commit
- A note that results are scoped to `openai/plugins` and `openai/role-based-plugins`

If no recent plugins match the requested window, say no additions were found in `openai/plugins` or `openai/role-based-plugins` for that period and suggest a wider window.

If no candidate is strong, say no strong match was found in the indexed repositories and suggest manually inspecting `openai/plugins` and `openai/role-based-plugins` or broadening the query.

## Do Not

| Temptation | Required Response |
| --- | --- |
| "Use local caches for broader coverage" | Do not. This skill only indexes `openai/plugins` and `openai/role-based-plugins`. |
| "Include fixture manifests for completeness" | Do not. Index only direct plugin manifests. |
| "Auto-install high-confidence matches" | Do not. Recommend and explain only. |
| "Claim this covers the Plugin Directory" | Do not. Say it only covers `openai/plugins` and `openai/role-based-plugins`. |
