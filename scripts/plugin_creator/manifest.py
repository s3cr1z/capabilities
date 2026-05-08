"""Capability + Claude Code plugin manifest helpers.

Loading + parsing ``capability.yaml`` is delegated to PyYAML rather than
``pydantic`` so the tool runs with only a stdlib + PyYAML dependency,
matching the rest of the repo's lightweight tooling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .paths import capabilities_dir

# Map of fields where ``capability.yaml`` and ``plugin.json`` use the
# same key with the same semantics.
_PASSTHROUGH_FIELDS: tuple[str, ...] = (
    "description",
    "homepage",
    "repository",
    "license",
    "keywords",
)

# Variable substitution: capability.yaml uses ``${CAPABILITY_ROOT}`` to
# reference the capability's own directory. Claude Code uses
# ``${CLAUDE_PLUGIN_ROOT}`` for the same concept.
_VAR_REPLACEMENT: tuple[tuple[str, str], ...] = (
    ("${CAPABILITY_ROOT}", "${CLAUDE_PLUGIN_ROOT}"),
)


@dataclass
class Capability:
    """A parsed ``capability.yaml`` plus its on-disk location."""

    name: str
    version: str
    description: str
    path: Path
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        """Directory name, used as the plugin name when ``name`` is missing."""
        return self.path.name

    @property
    def has_mcp(self) -> bool:
        return bool(self.raw.get("mcp", {}).get("servers"))

    @property
    def has_agents(self) -> bool:
        return (self.path / "agents").is_dir()

    @property
    def has_skills(self) -> bool:
        return (self.path / "skills").is_dir()

    @property
    def has_workers(self) -> bool:
        return (self.path / "workers").is_dir()


def load_capability(path: Path) -> Capability:
    """Load a single ``capability.yaml`` file.

    ``path`` may be either the capability directory or the manifest file
    inside it.
    """
    if path.is_dir():
        manifest = path / "capability.yaml"
    else:
        manifest = path

    if not manifest.is_file():
        raise FileNotFoundError(f"no capability.yaml at {manifest}")

    raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):  # pragma: no cover - defensive
        raise ValueError(f"{manifest}: expected mapping, got {type(raw).__name__}")

    name = str(raw.get("name") or manifest.parent.name)
    version = str(raw.get("version") or "0.0.0")
    description = str(raw.get("description") or "").strip()

    return Capability(
        name=name,
        version=version,
        description=description,
        path=manifest.parent.resolve(),
        raw=raw,
    )


def discover_capabilities(root: Path | None = None) -> list[Capability]:
    """Find every capability under ``capabilities/`` with a manifest."""
    base = capabilities_dir(root)
    found: list[Capability] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        manifest = entry / "capability.yaml"
        if not manifest.is_file():
            continue
        found.append(load_capability(manifest))
    return found


def _swap_capability_vars(value: Any) -> Any:
    """Translate ``${CAPABILITY_ROOT}`` → ``${CLAUDE_PLUGIN_ROOT}``."""
    if isinstance(value, str):
        out = value
        for src, dst in _VAR_REPLACEMENT:
            out = out.replace(src, dst)
        return out
    if isinstance(value, list):
        return [_swap_capability_vars(item) for item in value]
    if isinstance(value, dict):
        return {key: _swap_capability_vars(item) for key, item in value.items()}
    return value


def build_plugin_manifest(capability: Capability) -> dict[str, Any]:
    """Build a Claude Code ``plugin.json`` from a capability.

    Only fields with a Claude Code equivalent are emitted; Dreadnode-
    specific keys (``mcp``, ``checks``, ``dependencies``, ``workers``,
    ``schema``) are dropped here. MCP server config lands in a separate
    ``.mcp.json`` so it can use the standard Claude Code envelope.
    """
    raw = capability.raw
    plugin: dict[str, Any] = {
        "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
        "name": capability.name,
        "version": capability.version,
        "description": capability.description,
    }

    for field_name in _PASSTHROUGH_FIELDS:
        if field_name in plugin:  # pragma: no cover - already set
            continue
        value = raw.get(field_name)
        if value is None or value == "":
            continue
        plugin[field_name] = value

    author = raw.get("author")
    if isinstance(author, dict) and author:
        plugin["author"] = {
            key: author[key] for key in ("name", "email", "url") if key in author
        }

    if capability.has_mcp:
        # Reference the side-car .mcp.json. Claude Code reads either an
        # inline ``mcpServers`` block or a path string.
        plugin["mcpServers"] = "./.mcp.json"

    return plugin


def build_mcp_config(capability: Capability) -> dict[str, Any] | None:
    """Translate ``mcp.servers`` → Claude Code ``mcpServers`` block.

    Returns ``None`` for capabilities without an MCP block, which is the
    signal to skip writing a ``.mcp.json``.
    """
    servers = capability.raw.get("mcp", {}).get("servers")
    if not isinstance(servers, dict) or not servers:
        return None

    out_servers: dict[str, dict[str, Any]] = {}
    for server_name, server in servers.items():
        if not isinstance(server, dict):
            continue
        translated = _swap_capability_vars(server)
        # Drop Dreadnode-specific keys that Claude Code MCP doesn't grok.
        for key in ("init_timeout", "checks"):
            translated.pop(key, None)
        out_servers[server_name] = translated

    if not out_servers:
        return None

    return {"mcpServers": out_servers}


def marketplace_entry(
    capability: Capability, plugin_root: str = "./capabilities"
) -> dict[str, Any]:
    """Build a marketplace.json entry for ``capability``.

    Uses a relative-path source resolved against
    ``metadata.pluginRoot`` (set on the marketplace root). The
    marketplace lists each capability by its directory name so the
    source field stays short.
    """
    del plugin_root  # not currently used, kept for future override hooks
    raw = capability.raw

    entry: dict[str, Any] = {
        "name": capability.name,
        "source": capability.slug,
        "description": capability.description,
        "version": capability.version,
    }

    keywords = raw.get("keywords")
    if isinstance(keywords, list) and keywords:
        entry["keywords"] = list(keywords)

    extended: dict[str, Any] = {
        "capabilityYaml": f"./capabilities/{capability.slug}/capability.yaml",
        "components": {
            "agents": capability.has_agents,
            "skills": capability.has_skills,
            "mcp": capability.has_mcp,
            "workers": capability.has_workers,
        },
    }
    if "checks" in raw:
        extended["checks"] = raw["checks"]
    if "dependencies" in raw:
        extended["dependencies"] = raw["dependencies"]

    entry["extended"] = extended
    return entry
