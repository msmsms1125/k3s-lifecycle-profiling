# - step07_rollout_restart: 대상 Deployment(기본 nginx)에 대해 kubectl rollout restart 수행
#   restart 완료(rollout status 종료)까지의 duration과 그 구간의 자원 사용 패턴 측정
# - 각 run마다 START_EPOCH..END_EPOCH 구간을 기준으로 Netdata CSV 수집
#
# Artifacts (per run):
# - logs/redacted/step07_rollout_restart/run_<i>.log
#     STEP/RUN/START_EPOCH/END_EPOCH/T_total 기록
# - data/netdata/step07_rollout_restart/run_<i>/
#     system_cpu.csv
#     system_ram.csv
#     disk_util_mmcblk0.csv
#     disk_io_mmcblk0.csv
# - results/step07_rollout_restart/
#     (analysis/plot_step07.py가 생성하는 산출물: fig/stats 등)
#
# Env variables:
# - RUNS          : 반복 횟수 (default: 10)
# - DEPLOY        : 대상 deployment 이름 (default: nginx)
# - NETDATA_URL   : Netdata base URL (default: http://127.0.0.1:19999)
# - CPU_CHART     : CPU chart id (default: system.cpu)
# - RAM_CHART     : RAM chart id (default: system.ram)
# - DISK_UTIL_CHART : Disk util chart id (default: disk_util.mmcblk0)
# - IO_CHART      : IO chart id (default: system.io)
# - MANIFEST      : DEPLOY가 없을 때 apply할 manifest 경로
#                  (default: scripts/step04_apply_deployment/nginx-deployment.yaml)
#
# Epoch definition:
# - START_EPOCH : `kubectl rollout restart deploy/$DEPLOY` 실행 직전 timestamp
# - END_EPOCH   : `kubectl rollout status deploy/$DEPLOY` 완료 직후 timestamp
# - T_total     : END_EPOCH - START_EPOCH
# - export_csv  : [START_EPOCH, END_EPOCH] 구간을 Netdata API로 5초 평균(group=average, points=ceil(dur/5))으로 export
set -euo pipefail

STEP="step07_rollout_restart"
RUNS="${RUNS:-10}"
DEPLOY="${DEPLOY:-nginx}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs/redacted/${STEP}"
DATA_DIR="${REPO_ROOT}/data/netdata/${STEP}"
RES_DIR="${REPO_ROOT}/results/${STEP}"

NETDATA_URL="${NETDATA_URL:-http://127.0.0.1:19999}"

CPU_CHART="${CPU_CHART:-system.cpu}"
RAM_CHART="${RAM_CHART:-system.ram}"
DISK_UTIL_CHART="${DISK_UTIL_CHART:-disk_util.mmcblk0}"
IO_CHART="${IO_CHART:-system.io}"

MANIFEST="${MANIFEST:-${REPO_ROOT}/scripts/step04_apply_deployment/nginx-deployment.yaml}"

mkdir -p "${LOG_DIR}" "${DATA_DIR}" "${RES_DIR}"

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }; }
require_cmd date
require_cmd kubectl
require_cmd curl
require_cmd python3

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
  curl -sS -G "${NETDATA_URL}/api/v1/data" \
    --data-urlencode "chart=${chart}" \
    --data-urlencode "after=${after}" \
    --data-urlencode "before=${before}" \
    --data-urlencode "group=average" \
    --data-urlencode "points=${points}" \
    --data-urlencode "format=csv" \
    --data-urlencode "options=seconds,flip" \
    > "${out}"
}

prep_rollout() {
  kubectl wait --for=condition=Ready nodes --all --timeout=180s >/dev/null
  if ! kubectl get deploy/"${DEPLOY}" >/dev/null 2>&1; then
    [[ -f "${MANIFEST}" ]] && kubectl apply -f "${MANIFEST}" >/dev/null
  fi
  kubectl rollout status deploy/"${DEPLOY}" --timeout=300s >/dev/null
}

echo "[${STEP}] RUNS=${RUNS}, deploy=${DEPLOY}"
echo "[${STEP}] charts cpu=${CPU_CHART} ram=${RAM_CHART} disk_util=${DISK_UTIL_CHART} io=${IO_CHART}"

for i in $(seq 1 "${RUNS}"); do
  echo "== [${STEP}] run_${i}/${RUNS} =="

  prep_rollout

  RUN_LOG="${LOG_DIR}/run_${i}.log"
  RUN_DATA="${DATA_DIR}/run_${i}"
  mkdir -p "${RUN_DATA}"

  START_EPOCH="$(date +%s)"
  kubectl rollout restart deploy/"${DEPLOY}" >/dev/null
  kubectl rollout status deploy/"${DEPLOY}" --timeout=300s >/dev/null
  END_EPOCH="$(date +%s)"

  T_TOTAL="$((END_EPOCH - START_EPOCH))"

  cat > "${RUN_LOG}" <<EOL
STEP=${STEP}
RUN=${i}
START_EPOCH=${START_EPOCH}
END_EPOCH=${END_EPOCH}
T_total=${T_TOTAL}
EOL

  export_csv "${CPU_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_cpu.csv"
  export_csv "${RAM_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_ram.csv"
  export_csv "${DISK_UTIL_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_util_mmcblk0.csv"
  export_csv "${IO_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_io_mmcblk0.csv"
done

python3 "${REPO_ROOT}/analysis/plot_step07.py" --step "${STEP}"
echo "[DONE] ${STEP}"
