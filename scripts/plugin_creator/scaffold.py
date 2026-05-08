"""``scaffold`` subcommand: interactive new-plugin wizard.

Generates a brand-new capability/plugin skeleton under
``capabilities/<slug>/``. The skeleton is dual-shaped: it satisfies
both the Dreadnode capability layout (``capability.yaml``,
``skills/``, ``agents/``, ``mcp/``, ``tools/``) and the Claude Code
plugin layout (``.claude-plugin/plugin.json``, ``.mcp.json``).

We support five canonical templates plus a "full" template that
includes one of each surface. Pick interactively with ``scaffold``
(no args) or non-interactively with ``--name`` and ``--type``.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Literal

from .paths import capabilities_dir, repo_root

PluginType = Literal["command", "agent", "skill", "mcp", "full"]

_TYPES: tuple[PluginType, ...] = ("command", "agent", "skill", "mcp", "full")
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$")


@dataclass(slots=True)
class ScaffoldRequest:
    name: str
    plugin_type: PluginType
    description: str
    author: str = "Dreadnode"
    license: str = "MIT"


def scaffold(req: ScaffoldRequest, *, force: bool = False) -> Path:
    """Create the capability skeleton on disk. Returns its path."""
    if not _NAME_RE.match(req.name):
        raise ValueError(
            "name must be 3-40 chars, lowercase, alphanumeric + dashes "
            "(start with letter, end with letter/digit)"
        )

    target = capabilities_dir() / req.name
    if target.exists() and not force:
        raise FileExistsError(
            f"{target.relative_to(repo_root())} already exists (pass --force to overwrite)"
        )

    target.mkdir(parents=True, exist_ok=True)
    _write_capability_yaml(target, req)
    _write_readme(target, req)

    if req.plugin_type in {"skill", "full"}:
        _write_skill(target, req)
    if req.plugin_type in {"agent", "full"}:
        _write_agent(target, req)
    if req.plugin_type in {"command", "full"}:
        _write_command(target, req)
    if req.plugin_type in {"mcp", "full"}:
        _write_mcp(target, req)

    # Always emit Claude Code manifest + .mcp.json (when applicable) so
    # the new capability is immediately installable as a plugin.
    from .convert import convert_one
    from .manifest import load_capability

    convert_one(load_capability(target))
    return target


def interactive(stream_in=sys.stdin, stream_out=sys.stdout) -> ScaffoldRequest:
    """Prompt the user for the inputs needed to scaffold a plugin."""

    def ask(prompt: str, default: str | None = None) -> str:
        suffix = f" [{default}]" if default else ""
        stream_out.write(f"{prompt}{suffix}: ")
        stream_out.flush()
        line = stream_in.readline().strip()
        if not line and default is not None:
            return default
        return line

    name = ask("plugin name (kebab-case)")
    while not _NAME_RE.match(name):
        stream_out.write("  ↳ invalid name; try again\n")
        name = ask("plugin name (kebab-case)")

    stream_out.write("plugin types: " + ", ".join(_TYPES) + "\n")
    plugin_type = ask("plugin type", default="full")
    while plugin_type not in _TYPES:
        stream_out.write("  ↳ pick one of " + ", ".join(_TYPES) + "\n")
        plugin_type = ask("plugin type", default="full")

    description = ask("one-line description", default=f"{name} plugin")
    author = ask("author", default="Dreadnode")
    license_ = ask("license", default="MIT")

    return ScaffoldRequest(
        name=name,
        plugin_type=plugin_type,  # type: ignore[arg-type]
        description=description,
        author=author,
        license=license_,
    )


# -- file emitters ---------------------------------------------------------


def _write_capability_yaml(target: Path, req: ScaffoldRequest) -> None:
    body = dedent(
        f"""\
        schema: 1
        name: {req.name}
        version: "0.1.0"
        description: >
          {req.description}

        """
    )
    if req.plugin_type in {"agent", "full"}:
        body += "agents:\n  - agents/\n"
    if req.plugin_type in {"skill", "full"}:
        body += "skills:\n  - skills/\n"
    if req.plugin_type in {"mcp", "full"}:
        body += dedent(
            """\
            mcp:
              servers:
                {server_name}:
                  command: "uv"
                  args: ["run", "${{CAPABILITY_ROOT}}/mcp/server.py"]
                  init_timeout: 30

            """
        ).format(server_name=req.name.replace("-", "_"))

    body += dedent(
        f"""\
        author:
          name: {req.author}
        license: {req.license}
        keywords:
          - {req.name}
        """
    )
    (target / "capability.yaml").write_text(body, encoding="utf-8")


def _write_readme(target: Path, req: ScaffoldRequest) -> None:
    text = dedent(
        f"""\
        # {req.name}

        {req.description}

        Authored as a dual-shape Dreadnode capability + Claude Code plugin.

        ## Use as a Claude Code plugin

        ```bash
        /plugin marketplace add dreadnode/capabilities
        /plugin install {req.name}@dreadnode-capabilities
        ```

        ## Use as a Dreadnode capability

        ```bash
        dn capability install ./capabilities/{req.name}
        ```
        """
    )
    (target / "README.md").write_text(text, encoding="utf-8")


def _write_skill(target: Path, req: ScaffoldRequest) -> None:
    skill_dir = target / "skills" / req.name
    skill_dir.mkdir(parents=True, exist_ok=True)
    body = dedent(
        f"""\
        ---
        name: {req.name}
        description: Use when {req.description.lower().rstrip('.')}.
        ---

        # {req.name}

        Replace this body with the user-facing skill instructions.
        """
    )
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


def _write_agent(target: Path, req: ScaffoldRequest) -> None:
    agents_dir = target / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    body = dedent(
        f"""\
        ---
        name: {req.name}-agent
        description: Specialist agent for {req.description.lower().rstrip('.')}.
        ---

        # {req.name}-agent

        System prompt for the {req.name} specialist. Replace this with the
        agent's instructions.
        """
    )
    (agents_dir / f"{req.name}-agent.md").write_text(body, encoding="utf-8")


def _write_command(target: Path, req: ScaffoldRequest) -> None:
    commands_dir = target / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    body = dedent(
        f"""\
        ---
        description: Run the {req.name} workflow.
        ---

        # /{req.name}

        Replace this body with the slash-command prompt template.
        """
    )
    (commands_dir / f"{req.name}.md").write_text(body, encoding="utf-8")


def _write_mcp(target: Path, req: ScaffoldRequest) -> None:
    mcp_dir = target / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    server_name = req.name.replace("-", "_")
    body = dedent(
        f'''\
        # /// script
        # requires-python = ">=3.11"
        # dependencies = ["fastmcp>=2.0"]
        # ///
        """{req.name} MCP server (FastMCP)."""

        from __future__ import annotations

        from fastmcp import FastMCP

        mcp = FastMCP("{server_name}")


        @mcp.tool()
        def hello(name: str = "world") -> dict[str, str]:
            """Return a friendly greeting."""
            return {{"message": f"hello, {{name}}!"}}


        if __name__ == "__main__":
            mcp.run()
        '''
    )
    (mcp_dir / "server.py").write_text(body, encoding="utf-8")

    # Also write a tiny smoke test to match the repo's tests/<server>.py pattern.
    smoke = dedent(
        f'''\
        # /// script
        # requires-python = ">=3.11"
        # dependencies = ["fastmcp>=2.0"]
        # ///
        """Smoke test for {req.name}/mcp/server.py."""

        from __future__ import annotations

        import asyncio
        from pathlib import Path

        from fastmcp import Client


        async def main() -> None:
            here = Path(__file__).resolve().parent
            async with Client(str(here / "server.py")) as client:
                tools = await client.list_tools()
                names = sorted(t.name for t in tools)
                assert "hello" in names, names
                result = await client.call_tool("hello", {{"name": "ci"}})
                assert "hello, ci" in str(result)


        if __name__ == "__main__":
            asyncio.run(main())
        '''
    )
    (mcp_dir / "test_server.py").write_text(smoke, encoding="utf-8")


# -- non-interactive entrypoint -------------------------------------------


def from_args(name: str, plugin_type: str, description: str | None) -> ScaffoldRequest:
    if plugin_type not in _TYPES:
        raise ValueError(f"plugin_type must be one of {_TYPES}, got {plugin_type!r}")
    return ScaffoldRequest(
        name=name,
        plugin_type=plugin_type,  # type: ignore[arg-type]
        description=description or f"{name} plugin",
    )


def report(target: Path) -> str:
    """Pretty summary of what was scaffolded."""
    rel = target.relative_to(repo_root())
    files = sorted(p.relative_to(target) for p in target.rglob("*") if p.is_file())
    listing = "\n".join(f"  {rel}/{f}" for f in files)
    summary = json.dumps(
        {"path": str(rel), "files": [str(f) for f in files]},
        indent=2,
    )
    return f"scaffolded:\n{listing}\n\nsummary:\n{summary}"
