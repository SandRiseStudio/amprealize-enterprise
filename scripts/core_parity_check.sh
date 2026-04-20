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
EXCLUDES=(
  "--exclude=amprealize/enterprise/"
  "--exclude=amprealize/__pycache__/"
  "--exclude=amprealize/**/__pycache__/"
  "--exclude=amprealize/services/billing/"
  "--exclude=amprealize/services/sso/"
  "--exclude=amprealize/auth/providers/saml.py"
  "--exclude=amprealize/api.py"
)

drift_file="$(mktemp)"
rsync --dry-run --itemize-changes --archive --delete \
  "${EXCLUDES[@]}" \
  "${OSS_ROOT}/amprealize/" "${ENTERPRISE_ROOT}/amprealize/" > "${drift_file}" || true

changed_count=$(grep -cvE '^(cd|\.d|$)' "${drift_file}" || true)

if [[ "${changed_count}" -gt 0 ]]; then
  echo "Core parity drift detected (${changed_count} differing entries):" >&2
  grep -vE '^(cd|\.d|$)' "${drift_file}" >&2 || true
  rm -f "${drift_file}"
  exit 1
fi

rm -f "${drift_file}"
echo "core parity OK"
