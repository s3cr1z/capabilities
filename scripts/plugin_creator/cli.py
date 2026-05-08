"""Argparse front-end for ``python -m plugin_creator``.

Subcommands:

* ``convert``  — capability.yaml → plugin.json + .mcp.json
* ``scaffold`` — interactive (or ``--name`` / ``--type``) wizard for new plugins
* ``validate`` — manifest + frontmatter + executable-bit checks
* ``sync``     — marketplace.extended.json → marketplace.json
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import __version__
from .convert import convert_all, convert_target
from .scaffold import from_args, interactive, report, scaffold
from .sync_marketplace import sync
from .validate import ValidationError, validate_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plugin_creator",
        description="Generate Claude Code plugin manifests from Dreadnode capabilities.",
    )
    parser.add_argument(
        "--version", action="version", version=f"plugin_creator {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_convert = sub.add_parser(
        "convert", help="capability.yaml → plugin.json + .mcp.json"
    )
    p_convert.add_argument(
        "target",
        nargs="?",
        help="capability name or path (omit with --all to convert every capability)",
    )
    p_convert.add_argument(
        "--all", action="store_true", help="convert every capability"
    )
    p_convert.add_argument(
        "--dry-run", action="store_true", help="preview without writing"
    )

    p_scaffold = sub.add_parser(
        "scaffold", help="create a new capability/plugin skeleton"
    )
    p_scaffold.add_argument("--name", help="kebab-case plugin name")
    p_scaffold.add_argument(
        "--type",
        dest="plugin_type",
        choices=("command", "agent", "skill", "mcp", "full"),
        help="plugin template",
    )
    p_scaffold.add_argument("--description", help="one-line description")
    p_scaffold.add_argument(
        "--force", action="store_true", help="overwrite existing directory"
    )

    p_validate = sub.add_parser("validate", help="run manifest + frontmatter checks")
    p_validate.add_argument(
        "--external",
        action="store_true",
        help="also run `claude plugin validate` (requires Claude Code)",
    )

    p_sync = sub.add_parser(
        "sync", help="rebuild marketplace.extended.json + marketplace.json"
    )
    p_sync.add_argument(
        "--dry-run", action="store_true", help="preview without writing"
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "convert":
        return _cmd_convert(args)
    if args.command == "scaffold":
        return _cmd_scaffold(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "sync":
        return _cmd_sync(args)
    return 2  # pragma: no cover - argparse prevents this


def _cmd_convert(args: argparse.Namespace) -> int:
    if args.all and args.target:
        sys.stderr.write("convert: pass either a target or --all, not both\n")
        return 2
    if not args.all and not args.target:
        sys.stderr.write("convert: pass a target or use --all\n")
        return 2

    if args.all:
        results = convert_all(dry_run=args.dry_run)
    else:
        results = convert_target(args.target, dry_run=args.dry_run)

    for cap, files in results.items():
        for relpath, changed in files.items():
            mark = "*" if changed else " "
            print(f"{mark} {cap}/{relpath}")
    print(f"\nconverted {len(results)} capabilit{'y' if len(results) == 1 else 'ies'}")
    return 0


def _cmd_scaffold(args: argparse.Namespace) -> int:
    if args.name and args.plugin_type:
        req = from_args(args.name, args.plugin_type, args.description)
    elif args.name or args.plugin_type:
        sys.stderr.write(
            "scaffold: pass both --name and --type, or neither (interactive)\n"
        )
        return 2
    else:
        req = interactive()

    target = scaffold(req, force=args.force)
    print(report(target))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        warnings = validate_all(external=args.external)
    except ValidationError as exc:
        for err in exc.errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"warn: {warning}")
    print("validate: OK")
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    results = sync(dry_run=args.dry_run)
    for path, changed in results.items():
        mark = "*" if changed else " "
        print(f"{mark} {path}")
    return 0
