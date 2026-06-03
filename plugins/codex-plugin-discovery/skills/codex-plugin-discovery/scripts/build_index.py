#!/usr/bin/env python3
"""Build a searchable index for OpenAI Codex plugins."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MANIFEST_SCOPE = "plugins/*/.codex-plugin/plugin.json"
DEFAULT_REPOSITORY_URL = "https://github.com/openai/plugins"
ROLE_BASED_REPOSITORY_URL = "https://github.com/openai/role-based-plugins"


@dataclass(frozen=True)
class RepositorySource:
    repository: str
    cache_name: str


@dataclass(frozen=True)
class IndexSource:
    repo_dir: Path
    repository: str
    commit: str


DEFAULT_SOURCES = (
    RepositorySource(DEFAULT_REPOSITORY_URL, "openai-plugins"),
    RepositorySource(ROLE_BASED_REPOSITORY_URL, "openai-role-based-plugins"),
)


def run_git(args: list[str], cwd: Path | None = None) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def remote_head(repository_url: str = DEFAULT_REPOSITORY_URL) -> str:
    """Return the current HEAD SHA from the upstream repository."""
    output = run_git(["ls-remote", repository_url, "HEAD"])
    return output.split()[0]


def ensure_repo(cache_dir: Path, source: RepositorySource | None = None) -> Path:
    """Ensure an upstream plugin repository is cached and checked out."""
    selected = source or DEFAULT_SOURCES[0]
    repo_dir = cache_dir / selected.cache_name
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not repo_dir.exists():
        run_git(["clone", selected.repository, str(repo_dir)])
    else:
        if (repo_dir / ".git" / "shallow").exists():
            run_git(["fetch", "--unshallow", "origin"], cwd=repo_dir)
        run_git(["fetch", "origin", "HEAD"], cwd=repo_dir)
        run_git(["checkout", "--detach", "FETCH_HEAD"], cwd=repo_dir)

    return repo_dir


def scan_manifest_paths(repo_dir: Path) -> list[Path]:
    """Return direct plugin manifests, excluding nested fixtures."""
    return sorted((repo_dir / "plugins").glob("*/.codex-plugin/plugin.json"))


def read_json(path: Path) -> Any:
    """Read UTF-8 JSON from path."""
    return json.loads(path.read_text(encoding="utf-8"))


def as_list(value: Any) -> list[str]:
    """Normalize a scalar, list, or empty value into a list of strings."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and item != ""]
    return [str(value)]


def companion_surfaces(plugin_dir: Path) -> list[str]:
    """Detect companion surfaces adjacent to a plugin manifest."""
    surfaces = []
    for name in (
        "skills",
        "agents",
        "commands",
        "assets",
        ".app.json",
        ".mcp.json",
        "hooks.json",
    ):
        if (plugin_dir / name).exists():
            surfaces.append(name)
    return surfaces


def manifest_first_seen(manifest_path: Path, repo_dir: Path) -> dict[str, str]:
    """Return the commit and timestamp where a manifest first appeared."""
    rel_path = manifest_path.relative_to(repo_dir).as_posix()
    try:
        output = run_git(
            ["log", "--diff-filter=A", "--format=%H%x00%cI", "--", rel_path],
            cwd=repo_dir,
        )
    except subprocess.CalledProcessError as error:
        stderr = (error.stderr or "").strip()
        stdout = (error.stdout or "").strip()
        context_parts = []
        if stderr:
            context_parts.append(f"stderr: {stderr}")
        if stdout:
            context_parts.append(f"stdout: {stdout}")
        context = "; ".join(
            context_parts
        )
        suffix = f" ({context})" if context else ""
        raise ValueError(f"Failed to read first-seen history for {rel_path}{suffix}") from error

    entries = [line for line in output.splitlines() if line]
    if not entries:
        raise ValueError(f"No git add history found for {rel_path}")

    commit, committed_at = entries[-1].split("\x00", 1)
    return {
        "first_seen_at": committed_at,
        "first_seen_commit": commit,
    }


def build_plugin_record(
    manifest_path: Path,
    repo_dir: Path,
    source_repository: str = DEFAULT_REPOSITORY_URL,
    source_commit: str = "local",
) -> dict[str, Any]:
    """Build the recommendation fields for one plugin manifest."""
    manifest = read_json(manifest_path)
    interface = manifest.get("interface") or {}
    plugin_dir = manifest_path.parents[1]

    name = str(manifest.get("name") or plugin_dir.name)
    display_name = str(
        interface.get("displayName")
        or interface.get("display_name")
        or manifest.get("displayName")
        or manifest.get("display_name")
        or name
    )
    description = str(
        manifest.get("description")
        or interface.get("longDescription")
        or interface.get("shortDescription")
        or ""
    )
    category = str(interface.get("category") or manifest.get("category") or "")
    keywords = as_list(manifest.get("keywords"))
    capabilities = as_list(interface.get("capabilities") or manifest.get("capabilities"))
    repository = manifest.get("repository") or ""
    homepage = manifest.get("homepage") or ""
    plugin_path = plugin_dir.relative_to(repo_dir).as_posix()
    manifest_rel_path = manifest_path.relative_to(repo_dir).as_posix()
    surfaces = companion_surfaces(plugin_dir)
    first_seen = manifest_first_seen(manifest_path, repo_dir)

    search_parts = [
        name,
        display_name,
        description,
        category,
        *keywords,
        *capabilities,
        str(interface.get("shortDescription") or ""),
        str(interface.get("longDescription") or ""),
    ]

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
        "source_repository": source_repository,
        "source_commit": source_commit,
        "first_seen_at": first_seen["first_seen_at"],
        "first_seen_commit": first_seen["first_seen_commit"],
        "companion_surfaces": surfaces,
        "search_text": " ".join(part for part in search_parts if part).lower(),
    }


def source_record(repository: str, commit: str) -> dict[str, str]:
    """Return source metadata stored in the generated index."""
    return {
        "repository": repository,
        "commit": commit,
        "scope": MANIFEST_SCOPE,
    }


def build_index_from_sources(sources: list[IndexSource], output_path: Path) -> dict[str, Any]:
    """Build and write a plugin index from one or more repository sources."""
    source_entries = []
    plugins = []

    for source in sources:
        manifest_paths = scan_manifest_paths(source.repo_dir)
        if not manifest_paths:
            raise ValueError(f"No direct plugin manifests found under {source.repo_dir / 'plugins'}")

        source_entries.append(source_record(source.repository, source.commit))
        plugins.extend(
            build_plugin_record(
                manifest_path,
                source.repo_dir,
                source_repository=source.repository,
                source_commit=source.commit,
            )
            for manifest_path in manifest_paths
        )

    index = {
        "sources": source_entries,
        "plugins": plugins,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index


def build_index(
    repo_dir: Path,
    output_path: Path,
    upstream_sha: str,
    repository_url: str = DEFAULT_REPOSITORY_URL,
) -> dict[str, Any]:
    """Build and write the plugin index for one local repository source."""
    return build_index_from_sources(
        sources=[
            IndexSource(
                repo_dir=repo_dir,
                repository=repository_url,
                commit=upstream_sha,
            )
        ],
        output_path=output_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-dir", type=Path)
    args = parser.parse_args()

    if args.repo_dir:
        index = build_index(
            repo_dir=args.repo_dir,
            output_path=args.output,
            upstream_sha="local",
        )
    else:
        sources = []
        for repository_source in DEFAULT_SOURCES:
            upstream_sha = remote_head(repository_source.repository)
            repo_dir = ensure_repo(args.cache_dir, repository_source)
            sources.append(
                IndexSource(
                    repo_dir=repo_dir,
                    repository=repository_source.repository,
                    commit=upstream_sha,
                )
            )
        index = build_index_from_sources(sources=sources, output_path=args.output)

    summary = ", ".join(
        f"{source['repository']}@{source['commit'][:12]}"
        for source in index["sources"]
    )
    print(f"indexed {len(index['plugins'])} plugins from {len(index['sources'])} source(s): {summary}")


if __name__ == "__main__":
    main()
