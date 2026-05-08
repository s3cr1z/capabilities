"""Resolve repo-relative paths.

The plugin creator is always invoked from inside the capabilities repo,
either via ``python -m plugin_creator`` or ``just plugin-*``. We anchor
all relative paths to the repo root rather than the caller's CWD so the
tool works the same way from any subdirectory.
"""

from __future__ import annotations

from pathlib import Path


def repo_root(start: Path | None = None) -> Path:
    """Return the absolute path to the capabilities repo root.

    Walks up from ``start`` (or this file's location) until it finds a
    directory containing both ``capabilities/`` and ``justfile``. Raises
    ``RuntimeError`` if the marker is not found.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "capabilities").is_dir() and (candidate / "justfile").is_file():
            return candidate
    raise RuntimeError(
        "could not locate capabilities repo root from "
        f"{here} (no parent has both capabilities/ and justfile)"
    )


def capabilities_dir(root: Path | None = None) -> Path:
    """Return the directory holding individual capability folders."""
    return (root or repo_root()) / "capabilities"


def marketplace_dir(root: Path | None = None) -> Path:
    """Return the ``.claude-plugin`` directory at the repo root."""
    return (root or repo_root()) / ".claude-plugin"


def marketplace_json(root: Path | None = None) -> Path:
    """Path to the spec-clean ``marketplace.json`` (generated)."""
    return marketplace_dir(root) / "marketplace.json"


def marketplace_extended_json(root: Path | None = None) -> Path:
    """Path to the source-of-truth ``marketplace.extended.json``."""
    return marketplace_dir(root) / "marketplace.extended.json"
