# Codex Plugin Discovery

Codex Plugin Discovery is a Codex skill that helps find task-relevant Codex plugins from the official `openai/plugins` repository.

It is intentionally scoped: it searches metadata generated from `https://github.com/openai/plugins` only. It does not read local Codex plugin caches, does not inspect the full Codex App Plugin Directory, and does not install plugins automatically.

## Install As A Skill

After publishing this repository to GitHub, install the skill with:

```text
$skill-installer install https://github.com/<owner>/<repo>/tree/main/skills/codex-plugin-discovery
```

Restart Codex after installing so the skill metadata is picked up.

## Use

Ask for plugin recommendations with a task or category:

```text
What Codex plugin could help me make a slide deck?
```

```text
Find a Codex plugin for analyzing spreadsheets.
```

Broad questions such as "what plugins can I use?" are answered concisely. The skill does not dump the full index.

## Update The Index

The generated index is stored at:

```text
skills/codex-plugin-discovery/index/plugins-index.json
```

Regenerate it with:

```bash
cd skills/codex-plugin-discovery
python3 scripts/build_index.py --cache-dir .cache --output index/plugins-index.json
rm -rf .cache
```

## Distribute As A Plugin

This repository also includes a plugin package at:

```text
plugins/codex-plugin-discovery
```

The plugin bundles the same skill under `plugins/codex-plugin-discovery/skills/codex-plugin-discovery`.

## Verify

Run the skill tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s skills/codex-plugin-discovery/tests -v
```

Validate the skill and plugin manifests:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/codex-plugin-discovery
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/codex-plugin-discovery
```

## License

MIT
