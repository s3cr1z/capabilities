---
name: plugin-creator
description: Use when the user asks to "create plugin", "scaffold plugin", "new plugin", "convert capability", or otherwise wants to author a Claude Code plugin in the dreadnode/capabilities repo. Generates plugin.json + .mcp.json from existing capability.yaml manifests, scaffolds new plugins, validates manifests, and syncs the marketplace catalog.
---

# Plugin Creator

The Dreadnode capabilities repo dual-shapes every capability as both a Dreadnode capability **and** a Claude Code plugin. The Plugin Creator handles every transition between those two views without anyone having to remember the schema differences.

## When to use this skill

Trigger this skill whenever the user asks for any of:

- "create plugin" / "scaffold plugin" / "new plugin"
- "convert capability" / "regenerate plugin manifest"
- "sync marketplace" / "update marketplace catalog"
- "validate plugin" / "check plugin manifest"

## Commands

All four subcommands run from the repo root via `just plugin-*` (or `uv run --with pyyaml python -m scripts.plugin_creator <subcommand>` directly).

### `just plugin-convert [capability]`

Regenerates `.claude-plugin/plugin.json` and `.mcp.json` for one capability (or all of them with `--all` / no argument). Pass a capability name (`bloodhound`) or path; pulls metadata from `capability.yaml` and translates `${CAPABILITY_ROOT}` → `${CLAUDE_PLUGIN_ROOT}` in MCP server commands.

```bash
just plugin-convert                  # every capability
just plugin-convert bloodhound       # one capability
just plugin-convert --dry-run        # preview without writing
```

### `just plugin-scaffold`

Interactive wizard for a brand-new capability. Prompts for name (kebab-case), type (`command`, `agent`, `skill`, `mcp`, `full`), description, author, and license. Emits a fully-wired skeleton under `capabilities/<name>/` including the dual-shape `capability.yaml` + `.claude-plugin/plugin.json` + `.mcp.json` so it works as a Dreadnode capability AND a Claude Code plugin from minute one.

```bash
just plugin-scaffold                                # interactive
just plugin-scaffold --name foo --type full        # non-interactive
```

### `just plugin-sync`

Rebuilds the top-level `.claude-plugin/marketplace.extended.json` (source of truth, with Dreadnode metadata) and the spec-clean `.claude-plugin/marketplace.json` Claude Code reads. Hand-authored fields under each plugin's `extended` key are preserved; auto-generated fields are refreshed.

### `just plugin-validate`

Runs every check: marketplace JSON syntax, per-capability `plugin.json` consistency with `capability.yaml`, `.mcp.json` integrity, SKILL.md frontmatter, hook executable bits. Add `--external` to also run `claude plugin validate .` if Claude Code is installed locally.

## Workflow for end-to-end "make this capability installable as a Claude Code plugin"

```bash
just plugin-convert <name>     # generate plugin.json + .mcp.json
just plugin-sync               # update marketplace catalog
just plugin-validate           # confirm everything is consistent
```

Then users install the plugin with:

```bash
/plugin marketplace add dreadnode/capabilities
/plugin install <name>@dreadnode-capabilities
```

## Workflow for "create a new plugin"

```bash
just plugin-scaffold           # answer the prompts
just plugin-sync               # add it to the marketplace catalog
just plugin-validate
```

## Layout this skill expects

```
.claude-plugin/                       # marketplace catalog
├── marketplace.json                  # generated, spec-clean
└── marketplace.extended.json         # source of truth + Dreadnode metadata
capabilities/<name>/
├── capability.yaml                   # single source of truth
├── .claude-plugin/plugin.json        # generated
├── .mcp.json                         # generated when capability declares mcp.servers
├── skills/<name>/SKILL.md            # already at Claude Code's default location
├── agents/*.md                       # already at Claude Code's default location
├── commands/*.md                     # already at Claude Code's default location
├── mcp/*.py                          # FastMCP servers (referenced from .mcp.json)
└── tools/, workers/, tests/          # Dreadnode-only surfaces (not used by Claude Code)
scripts/plugin_creator/               # this tool
```

## Variable translation

| In `capability.yaml`     | In `.mcp.json`            | Notes                                  |
|--------------------------|---------------------------|----------------------------------------|
| `${CAPABILITY_ROOT}`     | `${CLAUDE_PLUGIN_ROOT}`   | Both resolve to the capability dir.    |
| `init_timeout`           | _stripped_                | Dreadnode-only key.                    |

## Don'ts

- Don't hand-edit `.claude-plugin/plugin.json` or `.mcp.json` — they're regenerated on every `convert`. Edit `capability.yaml` instead.
- Don't hand-edit `marketplace.json` — it's regenerated from `marketplace.extended.json` on every `sync`. Edit the extended file.
- Don't bypass pre-commit hooks. Run `just validate` and `just plugin-validate` before declaring work complete.
