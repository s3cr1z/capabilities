"""``sync`` subcommand: marketplace.extended.json → marketplace.json.

The extended file is the source of truth maintained by humans + the
``convert`` step. It includes Dreadnode-specific metadata under an
``extended`` key on each plugin entry (and at the marketplace root).
The spec-clean ``marketplace.json`` is what Claude Code actually reads;
we strip the ``extended`` key on the way out.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .manifest import discover_capabilities, marketplace_entry
from .paths import marketplace_extended_json, marketplace_json, repo_root

_MARKETPLACE_NAME = "dreadnode-capabilities"
_MARKETPLACE_OWNER = {"name": "Dreadnode", "url": "https://dreadnode.io"}
_PLUGIN_ROOT = "./capabilities"


def build_extended() -> dict[str, Any]:
    """Build a fresh ``marketplace.extended.json`` document.

    Used when the file does not yet exist. Existing files are preserved
    (with plugin entries refreshed in place) so humans can maintain
    extra ``extended`` metadata without it being clobbered.
    """
    plugins = [marketplace_entry(cap) for cap in discover_capabilities()]
    return {
        "$schema": "https://json.schemastore.org/claude-code-marketplace.json",
        "name": _MARKETPLACE_NAME,
        "description": (
            "Dreadnode capabilities exposed as Claude Code plugins. Each entry "
            "is generated from the matching capability.yaml; install one with "
            "`/plugin install <name>@dreadnode-capabilities`."
        ),
        "owner": dict(_MARKETPLACE_OWNER),
        "metadata": {
            "pluginRoot": _PLUGIN_ROOT,
            "extended": {"syncedFrom": "capability.yaml"},
        },
        "plugins": plugins,
    }


def refresh_extended(*, dry_run: bool = False) -> bool:
    """Refresh plugin entries inside ``marketplace.extended.json``.

    * If the file does not exist, write a freshly-built document.
    * If it does, replace each plugin entry whose ``name`` matches a
      discovered capability and append entries for new capabilities.
      Hand-authored ``extended`` keys are preserved by merging.
    """
    path = marketplace_extended_json()
    fresh = build_extended()

    if not path.is_file():
        return _write_json(path, fresh, dry_run)

    existing = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(existing, dict):  # pragma: no cover - defensive
        raise ValueError(f"{path}: expected mapping at top level")

    existing_plugins = {
        p["name"]: p for p in existing.get("plugins", []) if isinstance(p, dict)
    }

    merged_plugins: list[dict[str, Any]] = []
    for fresh_entry in fresh["plugins"]:
        name = fresh_entry["name"]
        prior = existing_plugins.pop(name, None)
        merged_plugins.append(_merge_plugin_entries(prior, fresh_entry))

    # Carry over plugins that exist in extended but no longer have a
    # capability source — humans may have hand-added entries pointing at
    # external sources (npm, github, ...). Don't drop those silently.
    for orphan in existing_plugins.values():
        merged_plugins.append(orphan)

    existing.setdefault("name", fresh["name"])
    existing.setdefault("owner", fresh["owner"])
    existing.setdefault("description", fresh["description"])
    existing.setdefault(
        "metadata",
        {"pluginRoot": _PLUGIN_ROOT, "extended": {"syncedFrom": "capability.yaml"}},
    )
    if "$schema" not in existing:
        existing["$schema"] = fresh["$schema"]
    existing["plugins"] = merged_plugins

    return _write_json(path, existing, dry_run)


def emit_marketplace(*, dry_run: bool = False) -> bool:
    """Write the spec-clean ``marketplace.json`` from the extended doc."""
    path = marketplace_extended_json()
    if not path.is_file():
        refresh_extended(dry_run=dry_run)
    extended = json.loads(path.read_text(encoding="utf-8"))
    spec = _strip_extended(extended)
    return _write_json(marketplace_json(), spec, dry_run)


def sync(*, dry_run: bool = False) -> dict[str, bool]:
    """Run the full pipeline: refresh extended → emit spec marketplace."""
    return {
        ".claude-plugin/marketplace.extended.json": refresh_extended(dry_run=dry_run),
        ".claude-plugin/marketplace.json": emit_marketplace(dry_run=dry_run),
    }


def _merge_plugin_entries(
    prior: dict[str, Any] | None, fresh: dict[str, Any]
) -> dict[str, Any]:
    """Refresh a plugin entry while preserving hand-authored extended keys."""
    if prior is None:
        return fresh

    merged = copy.deepcopy(fresh)

    # User-controlled top-level fields take precedence over the auto-
    # generated values: things like ``category``, ``tags``, ``author``.
    for key, value in prior.items():
        if key in {"name", "source", "description", "version", "extended"}:
            continue
        merged[key] = value

    # Merge ``extended`` blocks: auto-generated keys get refreshed,
    # user-added keys are preserved.
    prior_extended = (
        prior.get("extended") if isinstance(prior.get("extended"), dict) else {}
    )
    merged_extended = dict(prior_extended)
    merged_extended.update(merged.get("extended", {}))
    merged["extended"] = merged_extended
    return merged


def _strip_extended(doc: dict[str, Any]) -> dict[str, Any]:
    """Return ``doc`` with all ``extended`` keys removed (deep)."""
    out = copy.deepcopy(doc)
    if isinstance(out.get("metadata"), dict):
        out["metadata"].pop("extended", None)
        if not out["metadata"]:
            out.pop("metadata", None)
    plugins = out.get("plugins") or []
    for plugin in plugins:
        if isinstance(plugin, dict):
            plugin.pop("extended", None)
    return out


def _write_json(path: Path, data: dict[str, Any], dry_run: bool) -> bool:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    if dry_run:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


# Convenience for callers (e.g. justfile) that want to re-resolve paths.
def repo() -> Path:
    return repo_root()
