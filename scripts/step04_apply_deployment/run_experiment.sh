# - step04_apply_deployment: nginx Deployment를 apply하고, rollout 완료(READY)까지의 시간과 그 구간의 자원 사용 패턴 측정
# - 각 run마다 kubectl apply → rollout status 완료 시점을 기준으로 START/READY/END epoch를 기록, Netdata CSV 수집
#
# Artifacts (per run):
# - logs/redacted/step04_apply_deployment/run_<i>.log
#     STEP/RUN/START_EPOCH/READY_EPOCH/END_EPOCH 및 T_ready/T_total 기록
# - data/netdata/step04_apply_deployment/run_<i>/
#     system_cpu.csv
#     system_ram.csv
#     disk_util_mmcblk0.csv
#     disk_io_mmcblk0.csv (가능한 IO chart를 자동 탐색해 저장)
# - results/step04_apply_deployment/
#     (plot_step04.py가 생성하는 산출물: fig/stats 등)
#
# Env variables:
# - RUNS      : 반복 횟수 (default: 10)
# - NETDATA_URL : Netdata base URL (default: http://127.0.0.1:19999)
# - (내부 상수/경로)
#   - MANIFEST : scripts/step04_apply_deployment/nginx-deployment.yaml
#   - DISK_DEV : mmcblk0 기준 chart를 사용
#
# Epoch definition:
# - START_EPOCH : kubectl apply -f MANIFEST 직전 timestamp
# - READY_EPOCH : kubectl rollout status deployment/nginx 완료 직후 timestamp
# - END_EPOCH   : READY_EPOCH (본 step에서는 END=READY로 정의)
# - T_ready  = READY_EPOCH - START_EPOCH
# - T_total  = END_EPOCH - START_EPOCH (즉, T_total == T_ready)
# - export_csv는 [START_EPOCH, END_EPOCH] 구간을 Netdata API로 5초 평균(group=average, points=ceil(dur/5))으로 export
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

  if head -n 1 "${out}" 2>/dev/null | grep -q "No metrics where matched"; then
    : > "${out}"
  fi
}

cleanup_nginx() {
  kubectl delete -f "${MANIFEST}" --ignore-not-found >/dev/null 2>&1 || true
  kubectl delete deployment nginx --ignore-not-found >/dev/null 2>&1 || true
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

CPU_CHART="system.cpu"
RAM_CHART="system.ram"
DISK_UTIL_CHART="disk_util.mmcblk0"
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

  cleanup_nginx
done

python3 "${REPO_ROOT}/analysis/plot_step04.py" --step "${STEP}"

echo "[DONE] ${STEP}"
