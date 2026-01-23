#!/usr/bin/env bash
set -euo pipefail

STEP="step04_apply_deployment"
RUNS="${RUNS:-10}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs/redacted/${STEP}"
DATA_DIR="${REPO_ROOT}/data/netdata/${STEP}"
RES_DIR="${REPO_ROOT}/results/${STEP}"

NETDATA_URL="${NETDATA_URL:-http://127.0.0.1:19999}"
MANIFEST="${REPO_ROOT}/scripts/step04_apply_deployment/nginx-deployment.yaml"

mkdir -p "${LOG_DIR}" "${DATA_DIR}" "${RES_DIR}"

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }; }
require_cmd date
require_cmd python3
require_cmd kubectl
require_cmd curl

# ---------- helpers ----------
calc_points() {
  local after="$1" before="$2"
  local dur=$((before - after))
  local p=$(( (dur + 4) / 5 ))
  if (( p < 2 )); then p=2; fi
  echo "${p}"
}

export_csv() {
  local chart="$1" after="$2" before="$3" out="$4"
  local points; points="$(calc_points "${after}" "${before}")"
  curl -sS --max-time 8 -G "${NETDATA_URL}/api/v1/data" \
    --data-urlencode "chart=${chart}" \
    --data-urlencode "after=${after}" \
    --data-urlencode "before=${before}" \
    --data-urlencode "group=average" \
    --data-urlencode "points=${points}" \
    --data-urlencode "format=csv" \
    --data-urlencode "options=seconds,flip" \
    > "${out}" || true

  # netdata가 "No metrics..."를 주면 파일 비움 처리
  if head -n 1 "${out}" 2>/dev/null | grep -q "No metrics where matched"; then
    : > "${out}"
  fi
}

cleanup_nginx() {
  kubectl delete -f "${MANIFEST}" --ignore-not-found >/dev/null 2>&1 || true
  kubectl delete deployment nginx --ignore-not-found >/dev/null 2>&1 || true
  # rollout 중이던 리소스가 남아있을 수 있어 잠깐 정리 대기
  kubectl wait --for=delete deployment/nginx --timeout=120s >/dev/null 2>&1 || true
}

prep_apply() {
  cleanup_nginx
  if ! kubectl wait --for=condition=Ready nodes --all --timeout=120s >/dev/null; then
    echo "[ERROR] nodes not Ready. current status:"
    kubectl get nodes -o wide || true
    exit 1
  fi
}

# disk util은 이미 검증된 차트명으로 고정
CPU_CHART="system.cpu"
RAM_CHART="system.ram"
DISK_UTIL_CHART="disk_util.mmcblk0"
# IO는 환경마다 없을 수 있어서 후보를 돌려보고 성공하는 것만 사용
IO_CANDIDATES=("disk.io.mmcblk0" "disk_io.mmcblk0" "disk.io_mmcblk0")

pick_io_chart() {
  local after="$1" before="$2"
  for c in "${IO_CANDIDATES[@]}"; do
    local tmp="/tmp/netdata_io_probe_${c//[^a-zA-Z0-9]/_}.csv"
    export_csv "${c}" "${after}" "${before}" "${tmp}"
    if [[ -s "${tmp}" ]] && head -n 1 "${tmp}" | grep -q '^time,'; then
      echo "${c}"
      return 0
    fi
  done
  echo ""
}

echo "[${STEP}] RUNS=${RUNS}"
echo "[${STEP}] MANIFEST=${MANIFEST}"
echo "[${STEP}] DISK_UTIL_CHART=${DISK_UTIL_CHART}"

for i in $(seq 1 "${RUNS}"); do
  echo "== [${STEP}] run_${i}/${RUNS} =="

  prep_apply

  RUN_LOG="${LOG_DIR}/run_${i}.log"
  RUN_DATA="${DATA_DIR}/run_${i}"
  mkdir -p "${RUN_DATA}"

  START_EPOCH="$(date +%s)"
  kubectl apply -f "${MANIFEST}" >/dev/null

  # rollout 완료까지가 측정 구간
  kubectl rollout status deployment/nginx --timeout=600s >/dev/null
  READY_EPOCH="$(date +%s)"
  END_EPOCH="${READY_EPOCH}"

  T_READY="$((READY_EPOCH - START_EPOCH))"
  T_TOTAL="$((END_EPOCH - START_EPOCH))"

  cat > "${RUN_LOG}" <<EOF2
STEP=${STEP}
RUN=${i}
START_EPOCH=${START_EPOCH}
READY_EPOCH=${READY_EPOCH}
END_EPOCH=${END_EPOCH}
T_ready=${T_READY}
T_total=${T_TOTAL}
EOF2

  # netdata export (epoch로 정확히 절단)
  export_csv "${CPU_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_cpu.csv"
  export_csv "${RAM_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_ram.csv"
  export_csv "${DISK_UTIL_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_util_mmcblk0.csv"

  IO_CHART="$(pick_io_chart "${START_EPOCH}" "${END_EPOCH}")"
  if [[ -n "${IO_CHART}" ]]; then
    export_csv "${IO_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_io_mmcblk0.csv"
    echo "[${STEP}] run_${i}: IO_CHART=${IO_CHART}"
  else
    echo "[${STEP}] run_${i}: IO_CHART=<not found> (skip)"
  fi

  # 다음 run을 위해 nginx 제거(조건: nginx 없음 유지)
  cleanup_nginx
done

python3 "${REPO_ROOT}/analysis/plot_step04.py" --step "${STEP}"

echo "[DONE] ${STEP}"
