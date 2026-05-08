"""``validate`` subcommand.

Checks that the generated marketplace + per-capability plugin manifests
are well-formed, that referenced files exist, and that any executable
hook scripts have the executable bit set.

We don't shell out to ``claude plugin validate`` here because Claude
Code may not be installed on every contributor's machine; instead we
encode the schema rules we care about directly. The ``--external``
flag opts in to running ``claude plugin validate .`` as a final step
when the binary is available.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from .manifest import discover_capabilities
from .paths import marketplace_extended_json, marketplace_json, repo_root

# Keys Claude Code's marketplace.json schema accepts at the plugin entry
# level (see plugins-reference). Anything outside of these in the spec
# file is a synthesis bug — extended keys must be stripped during sync.
_ALLOWED_PLUGIN_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "source",
        "description",
        "version",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "category",
        "tags",
        "strict",
        "skills",
        "commands",
        "agents",
        "hooks",
        "mcpServers",
        "lspServers",
        "$schema",
    }
)


class ValidationError(Exception):
    """Raised when validation collects one or more failures."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


def validate_all(*, external: bool = False) -> list[str]:
    """Run every check. Returns a list of warning strings (no exception).

    Errors are raised as ``ValidationError``. Warnings are returned so a
    caller can surface them without failing the build.
    """
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_marketplace_files())
    errors.extend(_check_capabilities())
    errors.extend(_check_skill_frontmatter(warnings))
    errors.extend(_check_hook_scripts(warnings))

    if external:
        errors.extend(_check_external())

    if errors:
        raise ValidationError(errors)
    return warnings


def _check_marketplace_files() -> list[str]:
    errors: list[str] = []

    extended = marketplace_extended_json()
    if not extended.is_file():
        errors.append(
            f"missing {extended.relative_to(repo_root())} (run `just plugin-sync`)"
        )
        return errors

    try:
        extended_doc = json.loads(extended.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{extended.relative_to(repo_root())}: invalid JSON ({exc})")
        return errors

    spec = marketplace_json()
    if not spec.is_file():
        errors.append(
            f"missing {spec.relative_to(repo_root())} (run `just plugin-sync`)"
        )
    else:
        try:
            spec_doc = json.loads(spec.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{spec.relative_to(repo_root())}: invalid JSON ({exc})")
        else:
            errors.extend(_check_spec_doc(spec_doc))

    errors.extend(_check_extended_doc(extended_doc))
    return errors


def _check_extended_doc(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["marketplace.extended.json: expected an object at top level"]
    for required in ("name", "owner", "plugins"):
        if required not in doc:
            errors.append(
                f"marketplace.extended.json: missing required key {required!r}"
            )
    plugins = doc.get("plugins")
    if not isinstance(plugins, list):
        return errors + ["marketplace.extended.json: 'plugins' must be a list"]
    seen: set[str] = set()
    for entry in plugins:
        if not isinstance(entry, dict):
            errors.append("marketplace.extended.json: plugin entries must be objects")
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            errors.append("marketplace.extended.json: plugin entry missing 'name'")
            continue
        if name in seen:
            errors.append(f"marketplace.extended.json: duplicate plugin name {name!r}")
        seen.add(name)
        if "source" not in entry:
            errors.append(
                f"marketplace.extended.json: plugin {name!r} missing 'source'"
            )
    return errors


def _check_spec_doc(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    plugins = doc.get("plugins")
    if not isinstance(plugins, list):
        return ["marketplace.json: 'plugins' must be a list"]
    for entry in plugins:
        if not isinstance(entry, dict):
            errors.append("marketplace.json: plugin entries must be objects")
            continue
        bad = set(entry.keys()) - _ALLOWED_PLUGIN_KEYS
        if bad:
            errors.append(
                "marketplace.json: plugin "
                f"{entry.get('name', '?')!r} has non-spec keys "
                + ", ".join(sorted(bad))
                + " (sync should have stripped them)"
            )
    return errors


def _check_capabilities() -> list[str]:
    errors: list[str] = []
    for cap in discover_capabilities():
        plugin_json = cap.path / ".claude-plugin" / "plugin.json"
        if not plugin_json.is_file():
            errors.append(f"{cap.slug}: missing .claude-plugin/plugin.json")
            continue
        try:
            plugin = json.loads(plugin_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{cap.slug}: invalid plugin.json ({exc})")
            continue

        if plugin.get("name") != cap.name:
            errors.append(
                f"{cap.slug}: plugin.json name {plugin.get('name')!r} != capability name {cap.name!r}"
            )
        if plugin.get("version") != cap.version:
            errors.append(
                f"{cap.slug}: plugin.json version {plugin.get('version')!r} != "
                f"capability version {cap.version!r}"
            )

        if cap.has_mcp:
            mcp_path = cap.path / ".mcp.json"
            if not mcp_path.is_file():
                errors.append(
                    f"{cap.slug}: capability declares mcp.servers but no .mcp.json was generated"
                )
                continue
            try:
                mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{cap.slug}: invalid .mcp.json ({exc})")
                continue
            if "mcpServers" not in mcp:
                errors.append(f"{cap.slug}: .mcp.json missing 'mcpServers' key")
    return errors


def _check_skill_frontmatter(warnings: list[str]) -> list[str]:
    errors: list[str] = []
    for cap in discover_capabilities():
        skills_dir = cap.path / "skills"
        if not skills_dir.is_dir():
            continue
        for skill_md in skills_dir.glob("*/SKILL.md"):
            frontmatter, body = _split_frontmatter(skill_md.read_text(encoding="utf-8"))
            if frontmatter is None:
                warnings.append(
                    f"{skill_md.relative_to(repo_root())}: no YAML frontmatter"
                )
                continue
            try:
                fm = yaml.safe_load(frontmatter)
            except yaml.YAMLError as exc:
                errors.append(
                    f"{skill_md.relative_to(repo_root())}: bad frontmatter YAML ({exc})"
                )
                continue
            if not isinstance(fm, dict):
                errors.append(
                    f"{skill_md.relative_to(repo_root())}: frontmatter must be a mapping"
                )
                continue
            if "description" not in fm:
                warnings.append(
                    f"{skill_md.relative_to(repo_root())}: missing 'description' in frontmatter"
                )
            if not body.strip():
                warnings.append(
                    f"{skill_md.relative_to(repo_root())}: empty body below frontmatter"
                )
    return errors


def _check_hook_scripts(warnings: list[str]) -> list[str]:
    errors: list[str] = []
    for cap in discover_capabilities():
        hooks_json = cap.path / "hooks" / "hooks.json"
        if not hooks_json.is_file():
            continue
        try:
            hooks_doc = json.loads(hooks_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{cap.slug}: invalid hooks/hooks.json ({exc})")
            continue
        for path in _iter_hook_command_paths(hooks_doc, cap.path):
            if not path.exists():
                errors.append(f"{cap.slug}: hook command not found: {path}")
                continue
            mode = path.stat().st_mode
            if path.suffix in {"", ".sh", ".py"} and not (mode & stat.S_IXUSR):
                warnings.append(
                    f"{cap.slug}: hook command {path.name} not executable (chmod +x recommended)"
                )
    return errors


def _check_external() -> list[str]:
    binary = shutil.which("claude")
    if binary is None:
        return [
            "external check requested but `claude` binary not on PATH; install Claude Code or drop --external"
        ]
    proc = subprocess.run(  # noqa: S603 - intentional external invocation
        [binary, "plugin", "validate", str(repo_root())],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return [
            f"`claude plugin validate` failed:\n{proc.stdout}\n{proc.stderr}".strip()
        ]
    return []


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    return parts[1], parts[2]


def _iter_hook_command_paths(doc: Any, plugin_root: Path) -> Iterable[Path]:
    if not isinstance(doc, dict):
        return
    hooks = doc.get("hooks") or {}
    if not isinstance(hooks, dict):
        return
    for events in hooks.values():
        if not isinstance(events, list):
            continue
        for matcher in events:
            if not isinstance(matcher, dict):
                continue
            inner = matcher.get("hooks") or []
            if not isinstance(inner, list):
                continue
            for hook in inner:
                if not isinstance(hook, dict):
                    continue
                if hook.get("type") != "command":
                    continue
                cmd = hook.get("command")
                if not isinstance(cmd, str):
                    continue
                resolved = cmd.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root))
                first = resolved.split()[0] if resolved.split() else resolved
                path = Path(first)
                if path.is_absolute() or first.startswith("/"):
                    yield path
                else:
                    yield (plugin_root / first).resolve()


def is_executable(path: Path) -> bool:
    """Return True iff ``path`` exists and has owner-execute set."""
    return path.is_file() and bool(path.stat().st_mode & stat.S_IXUSR)


def ensure_executable(path: Path) -> bool:
    """Set the executable bit on ``path`` if missing. Returns True if changed."""
    if not path.is_file():
        return False
    mode = path.stat().st_mode
    new_mode = mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    if new_mode == mode:
        return False
    os.chmod(path, new_mode)
    return True
