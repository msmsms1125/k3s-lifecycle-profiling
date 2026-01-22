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
  local points=$(( duration / 5 ))
  (( points < 1 )) && points=1

  local url="${NETDATA_URL}/api/v1/data?chart=${chart}&after=${after}&before=${before}&format=csv&group=average&points=${points}"

  # 디버그: 진짜 요청 URL 확인용(원하면 주석 처리)
  echo "[netdata_export] $url" >&2

  curl -fsSL "$url" -o "$out"
}
