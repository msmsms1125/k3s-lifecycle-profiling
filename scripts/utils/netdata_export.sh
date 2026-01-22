#!/usr/bin/env bash
set -euo pipefail

NETDATA_URL="${NETDATA_URL:-http://127.0.0.1:19999}"

# export_csv <chart> <after_epoch> <before_epoch> <out_csv>
export_csv() {
  local chart="$1"
  local after="$2"
  local before="$3"
  local out="$4"

  local duration=$(( before - after ))
  # 5초 간격이면 points ≈ duration/5
  local points=$(( duration / 5 ))
  (( points < 1 )) && points=1

  curl -fsSL \
    "${NETDATA_URL}/api/v1/data?chart=${chart}&after=${after}&before=${before}&format=csv&group=average&points=${points}" \
    -o "${out}"
}

