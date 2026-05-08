# Capabilities repo — local development recipes
# https://github.com/casey/just

set dotenv-load := false

default:
    @just --list

# Validate all capabilities (pass strict="true" for CI-level checks)
validate strict="false":
    #!/usr/bin/env bash
    set -euo pipefail
    cmd=(uv run --with dreadnode dreadnode capability validate capabilities)
    [[ "{{ strict }}" == "true" ]] && cmd+=(--strict)
    "${cmd[@]}"

# Security scan all skills (pass capability to scan one, behavioral="true" for deep analysis)
security-scan capability="" behavioral="false":
    #!/usr/bin/env bash
    set -euo pipefail
    cmd=(./scripts/security-scan.sh)
    [[ "{{ behavioral }}" == "true" ]] && cmd+=(--behavioral)
    [[ -n "{{ capability }}" ]] && cmd+=("{{ capability }}")
    "${cmd[@]}"

# Run security scan tests
test-security-scan:
    ./scripts/test_security_scan.sh -v

# Sync all capabilities to local platform (requires running API + SDK profile)
sync-local force="false":
    #!/usr/bin/env bash
    set -euo pipefail
    server="${DREADNODE_LOCAL_API_URL:-http://localhost:8000}"
    cmd=(uv run --with dreadnode dreadnode capability sync capabilities --server "${server}" --organization dreadnode)
    [[ -n "${DREADNODE_API_KEY:-}" ]] && cmd+=(--api-key "${DREADNODE_API_KEY}")
    [[ "{{ force }}" == "true" ]] && cmd+=(--force)
    "${cmd[@]}"

# --- Claude Code plugin creator ----------------------------------------------

# Convert capability.yaml -> plugin.json + .mcp.json (one capability or --all)
plugin-convert *args="--all":
    uv run --with pyyaml python -m scripts.plugin_creator convert {{ args }}

# Interactive (or --name/--type) wizard for a new capability + Claude Code plugin
plugin-scaffold *args="":
    uv run --with pyyaml python -m scripts.plugin_creator scaffold {{ args }}

# Rebuild marketplace.extended.json + marketplace.json from current capabilities
plugin-sync *args="":
    uv run --with pyyaml python -m scripts.plugin_creator sync {{ args }}

# Validate plugin manifests, marketplace catalog, frontmatter, executable bits
plugin-validate *args="":
    uv run --with pyyaml python -m scripts.plugin_creator validate {{ args }}

# -----------------------------------------------------------------------------

# Mirror repo capabilities into ~/.dreadnode/capabilities
sync-dreadnode-files:
    #!/usr/bin/env bash
    set -euo pipefail
    target="${HOME}/.dreadnode/capabilities"
    mkdir -p "${target}"
    for d in capabilities/*/capability.yaml; do
        [[ -f "${d}" ]] || continue
        cap=$(basename "$(dirname "${d}")")
        rsync -a --delete --delete-excluded --exclude '.DS_Store' "capabilities/${cap}/" "${target}/${cap}/"
    done
    for existing in "${target}"/*/; do
        [[ -d "${existing}" ]] || continue
        cap=$(basename "${existing}")
        [[ -f "capabilities/${cap}/capability.yaml" ]] || rm -rf "${existing}"
    done
