#!/usr/bin/env python3
"""List plugins first added recently in the generated Codex plugin index."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def load_index(path: Path) -> dict[str, Any]:
    """Read a plugin index from JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def positive_int(value: str) -> int:
    """Argparse type for positive integer values."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp from the generated index."""
    normalized = value
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def recent_plugins(
    index: dict[str, Any],
    days: int = 7,
    limit: int = 10,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return plugins first seen within the requested number of days."""
    if days < 1:
        raise ValueError("days must be positive")
    if limit < 1:
        raise ValueError("limit must be positive")

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    cutoff = current_time - timedelta(days=days)
    results = []

    for plugin in index.get("plugins", []):
        first_seen_at = plugin.get("first_seen_at")
        if not first_seen_at:
            continue

        first_seen = parse_timestamp(str(first_seen_at))
        if first_seen >= cutoff:
            result = dict(plugin)
            result["_first_seen_sort"] = first_seen
            results.append(result)

    results.sort(key=lambda plugin: plugin["_first_seen_sort"], reverse=True)
    for plugin in results:
        del plugin["_first_seen_sort"]
    return results[:limit]


def render_results(results: list[dict[str, Any]], index: dict[str, Any], days: int) -> str:
    """Render recent plugins as Markdown-ish output."""
    boundary = "Results only cover openai/plugins"
    source = index.get("source") or {}
    commit = source.get("commit")
    lines = [boundary]
    if commit:
        lines[0] = f"{lines[0]} (commit: {commit})"

    if not results:
        lines.extend(
            [
                "",
                f"No plugins were first added in the last {days} days.",
                "Try a wider window with --days 14 or --days 30.",
            ]
        )
        return "\n".join(lines)

    lines.append("")
    for position, plugin in enumerate(results, start=1):
        display_name = plugin.get("display_name") or plugin.get("name") or "Unknown plugin"
        name = plugin.get("name") or display_name
        category = plugin.get("category") or "Uncategorized"
        location = plugin.get("repository") or plugin.get("homepage") or plugin.get("plugin_path") or ""
        first_seen_at = plugin.get("first_seen_at") or "unknown"
        first_seen_commit = plugin.get("first_seen_commit")

        lines.append(f"{position}. {display_name} ({name})")
        lines.append(f"   Category: {category}")
        lines.append(f"   First seen: {first_seen_at}")
        if first_seen_commit:
            lines.append(f"   First seen commit: {first_seen_commit}")
        lines.append(f"   Source: {location}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=Path("index/plugins-index.json"))
    parser.add_argument("--days", type=positive_int, default=7)
    parser.add_argument("--limit", type=positive_int, default=10)
    args = parser.parse_args()

    index = load_index(args.index)
    results = recent_plugins(index, days=args.days, limit=args.limit)
    print(render_results(results, index, days=args.days))


if __name__ == "__main__":
    main()
