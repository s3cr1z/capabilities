"""Plugin Creator for the Dreadnode capabilities repo.

Bridges Dreadnode capabilities and Claude Code plugins. Each
``capabilities/<name>/`` directory becomes simultaneously a Dreadnode
capability (driven by ``capability.yaml``) and a Claude Code plugin
(driven by a generated ``.claude-plugin/plugin.json`` + ``.mcp.json``).

The tool has four subcommands:

* ``convert``  — regenerate plugin.json + .mcp.json from a capability's
  ``capability.yaml``.
* ``scaffold`` — interactive wizard for a brand-new plugin (command,
  agent, skill, mcp, full).
* ``validate`` — JSON / YAML / frontmatter / executable-bit / Claude
  Code spec checks across the marketplace.
* ``sync``     — flatten ``marketplace.extended.json`` (source of truth
  with Dreadnode metadata) into a spec-clean ``marketplace.json`` Claude
  Code can read.
"""

from __future__ import annotations

__version__ = "0.1.0"
