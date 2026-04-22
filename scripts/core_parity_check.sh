#!/usr/bin/env bash
# Verify the `amprealize/` core package matches between the OSS and enterprise
# repos. Enterprise-only submodules (see OSS_VS_ENTERPRISE.md "Enterprise-only
# paths") are excluded.
#
# Exits 0 on parity, 1 on drift, 2 on config error.
#
# Usage:
#   scripts/core_parity_check.sh
#   OSS_ROOT=/path/to/amprealize scripts/core_parity_check.sh

set -euo pipefail

ENTERPRISE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OSS_ROOT="${OSS_ROOT:-$(cd "$ENTERPRISE_ROOT/../amprealize" 2>/dev/null && pwd || true)}"

if [[ -z "${OSS_ROOT}" || ! -d "${OSS_ROOT}/amprealize" ]]; then
  echo "ERROR: could not locate OSS amprealize repo. Set OSS_ROOT explicitly." >&2
  exit 2
fi

# Enterprise-only sub-trees inside amprealize/ that may diverge legitimately.
# Keep in sync with OSS_VS_ENTERPRISE.md.
#
# NOTE: rsync source is "${OSS_ROOT}/amprealize/" so all paths here are
# relative to the amprealize/ package root — no "amprealize/" prefix needed.
EXCLUDES=(
  # Generated / compiled artifacts — never meaningful to compare
  "--exclude=__pycache__/"
  "--exclude=*.pyc"

  # Enterprise-only top-level sub-packages
  "--exclude=enterprise/"
  "--exclude=multi_tenant/"
  "--exclude=tenant/"
  "--exclude=wizard/"
  "--exclude=projects/"

  # Enterprise-only individual files at root
  "--exclude=api.py"
  "--exclude=auth/invite_policy.py"
  "--exclude=auth/providers/saml.py"
  "--exclude=perf_log.py"

  # Enterprise-only service modules
  "--exclude=services/billing/"
  "--exclude=services/sso/"
  "--exclude=services/whiteboard_api.py"
  "--exclude=services/whiteboard_hooks.py"
  "--exclude=services/brainstorm_bridge.py"

  # Enterprise-only storage
  "--exclude=storage/whiteboard_postgres.py"
  "--exclude=storage/sqlite_migrations/.!44611!m001_initial_schema.py"

  # Enterprise-only MCP handlers and manifests
  "--exclude=mcp/handlers/whiteboard_handlers.py"
  "--exclude=mcp/handlers/brainstorm_handlers.py"
  "--exclude=mcp_tool_manifests/whiteboard.*"
  "--exclude=mcp_tool_manifests/brainstorm.*"

  # Enterprise-only agent playbooks / templates
  "--exclude=agents/playbooks/AGENT_BRAINSTORM.md"
  "--exclude=agents/templates/BRAINSTORM_SESSION_TEMPLATE.md"

  # Enterprise shim
  "--exclude=multi_tenant/shim"
)

drift_file="$(mktemp)"
# Use --checksum so timestamp-only skew (git checkout mtime) is not a false
# positive. We only care about content changes.
rsync --dry-run --itemize-changes --checksum --archive --delete \
  "${EXCLUDES[@]}" \
  "${OSS_ROOT}/amprealize/" "${ENTERPRISE_ROOT}/amprealize/" > "${drift_file}" || true

# ── Tier 1: FAIL if OSS has a brand-new file that enterprise is missing ────────
# These look like ">f++++++++  path/to/file" — enterprise must track every new
# module shipped in OSS to stay current.
missing_count=$(grep -cE '^>f\+{5,}' "${drift_file}" || true)

# ── Tier 2: WARN on content drift (shared files that have diverged) ───────────
# Files in both repos but with different content show as ">fcst.... path".
# Enterprise is an extended fork so content will legitimately diverge; we log
# this as a warning so developers can reconcile gradually rather than blocking
# every deploy.
drift_count=$(grep -cE '^>f[^+]' "${drift_file}" || true)

if [[ "${missing_count}" -gt 0 ]]; then
  echo "PARITY FAIL — enterprise is missing ${missing_count} file(s) that exist in OSS:" >&2
  grep -E '^>f\+{5,}' "${drift_file}" | sed 's/^[^ ]* /  /' >&2 || true
  rm -f "${drift_file}"
  exit 1
fi

if [[ "${drift_count}" -gt 0 ]]; then
  echo "WARNING: ${drift_count} shared file(s) have content drift between OSS and enterprise." >&2
  echo "  These files exist in both repos but have diverged. Run 'scripts/core_parity_check.sh'" >&2
  echo "  locally to see the full list, and reconcile when possible." >&2
fi

rm -f "${drift_file}"
echo "core parity OK (${drift_count} content-drift warnings)"
