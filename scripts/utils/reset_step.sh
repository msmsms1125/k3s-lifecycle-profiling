#!/usr/bin/env bash
set -euo pipefail

STEP="${1:-}"
if [[ -z "$STEP" ]]; then
  echo "usage: $0 <step_dir_name>   e.g) step01_system_idle"
  exit 1
fi

echo "[reset] step = $STEP"
rm -rf "data/netdata/${STEP}" "results/${STEP}" "logs/redacted/${STEP}"
mkdir -p "data/netdata/${STEP}" "results/${STEP}" "logs/redacted/${STEP}"
echo "[reset] done"
