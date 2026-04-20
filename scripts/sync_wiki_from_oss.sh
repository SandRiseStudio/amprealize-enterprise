#!/usr/bin/env bash
# Mirror public wiki domains (research/, infra/, ai-learning/) from the OSS
# amprealize repo into the enterprise repo's wiki/ directory. Platform/ is
# enterprise-only and is never overwritten.
#
# Usage:
#   scripts/sync_wiki_from_oss.sh                 # use sibling ../amprealize
#   OSS_ROOT=/path/to/amprealize scripts/sync_wiki_from_oss.sh
#   scripts/sync_wiki_from_oss.sh --check         # no-op, exit non-zero if drift
#
# Idempotent. Safe to run in CI (see .github/workflows/deploy-prod.yml).

set -euo pipefail

ENTERPRISE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OSS_ROOT="${OSS_ROOT:-$(cd "$ENTERPRISE_ROOT/../amprealize" 2>/dev/null && pwd || true)}"

if [[ -z "${OSS_ROOT}" || ! -d "${OSS_ROOT}/wiki" ]]; then
  echo "ERROR: could not locate OSS amprealize repo. Set OSS_ROOT explicitly." >&2
  exit 2
fi

DOMAINS=(research infra ai-learning)
MODE="sync"
if [[ "${1:-}" == "--check" ]]; then
  MODE="check"
fi

drift=0
for domain in "${DOMAINS[@]}"; do
  src="${OSS_ROOT}/wiki/${domain}/"
  dst="${ENTERPRISE_ROOT}/wiki/${domain}/"

  if [[ ! -d "${src}" ]]; then
    echo "skip: OSS wiki/${domain} does not exist"
    continue
  fi

  mkdir -p "${dst}"

  if [[ "${MODE}" == "check" ]]; then
    if ! diff -rq "${src}" "${dst}" >/dev/null 2>&1; then
      echo "drift: wiki/${domain}"
      drift=1
    fi
  else
    rsync -a --delete "${src}" "${dst}"
    echo "synced: wiki/${domain}"
  fi
done

if [[ "${MODE}" == "check" && "${drift}" -ne 0 ]]; then
  echo "Wiki content drift detected. Run scripts/sync_wiki_from_oss.sh to fix." >&2
  exit 1
fi

echo "done."
