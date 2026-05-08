"""``convert`` subcommand: capability.yaml → plugin.json + .mcp.json."""

from __future__ import annotations

import json
from pathlib import Path

from .manifest import (
    Capability,
    build_mcp_config,
    build_plugin_manifest,
    discover_capabilities,
    load_capability,
)


def _write_json(path: Path, data: dict, dry_run: bool) -> bool:
    """Write ``data`` as pretty JSON to ``path``. Returns True if changed."""
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    if dry_run:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _delete_if_present(path: Path, dry_run: bool) -> bool:
    if not path.exists():
        return False
    if dry_run:
        return True
    path.unlink()
    return True


def convert_one(cap: Capability, *, dry_run: bool = False) -> dict[str, bool]:
    """Convert a single capability into Claude Code plugin manifests.

    Returns a small dict of which artifacts changed, keyed by the
    relative path inside the capability directory.
    """
    plugin_path = cap.path / ".claude-plugin" / "plugin.json"
    mcp_path = cap.path / ".mcp.json"

    changed: dict[str, bool] = {}
    changed[".claude-plugin/plugin.json"] = _write_json(
        plugin_path, build_plugin_manifest(cap), dry_run
    )

    mcp_config = build_mcp_config(cap)
    if mcp_config is None:
        changed[".mcp.json"] = _delete_if_present(mcp_path, dry_run)
    else:
        changed[".mcp.json"] = _write_json(mcp_path, mcp_config, dry_run)
    return changed


def convert_all(*, dry_run: bool = False) -> dict[str, dict[str, bool]]:
    """Convert every discovered capability."""
    out: dict[str, dict[str, bool]] = {}
    for cap in discover_capabilities():
        out[cap.slug] = convert_one(cap, dry_run=dry_run)
    return out


def convert_target(target: str, *, dry_run: bool = False) -> dict[str, dict[str, bool]]:
    """Convert one capability identified by name or path."""
    candidate = Path(target)
    if candidate.is_dir():
        cap = load_capability(candidate)
    else:
        from .paths import capabilities_dir

        cap = load_capability(capabilities_dir() / target)
    return {cap.slug: convert_one(cap, dry_run=dry_run)}
