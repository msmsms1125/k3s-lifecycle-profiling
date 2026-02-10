# - step06_scale_up_down: 특정 Deployment(기본 nginx)를 scale down(3→1) 후 scale up(1→3),
#   각 구간의 duration과 전체 구간의 자원 사용 패턴 측정
# - 1 run = (down 구간) + (up 구간) 연속 수행이며, Netdata CSV는 DOWN_START..UP_END 전체 구간으로 export
#
# Artifacts (per run):
# - logs/redacted/step06_scale_up_down/run_<i>.log
#     START_EPOCH/READY_EPOCH/END_EPOCH
#     DOWN_START_EPOCH/DOWN_END_EPOCH, UP_START_EPOCH/UP_END_EPOCH
#     T_down/T_up/T_total 기록
# - data/netdata/step06_scale_up_down/run_<i>/
#     system_cpu.csv
#     system_ram.csv
#     disk_util_mmcblk0.csv
#     disk_io_mmcblk0.csv
# - results/step06_scale_up_down/
#     (analysis/plot_step06.py가 생성하는 산출물: fig/stats 등)
#
# Env variables:
# - RUNS          : 반복 횟수 (default: 10)
# - DEPLOY        : 대상 deployment 이름 (default: nginx)
# - REPLICAS_HIGH : scale up 목표 replicas (default: 3)
# - REPLICAS_LOW  : scale down 목표 replicas (default: 1)
# - NETDATA_URL   : Netdata base URL (default: http://127.0.0.1:19999)
# - CPU_CHART     : CPU chart id (default: system.cpu)
# - RAM_CHART     : RAM chart id (default: system.ram)
# - DISK_UTIL_CHART : Disk util chart id (default: disk_util.mmcblk0)
# - IO_CHART      : IO chart id (default: system.io)
# - MANIFEST      : DEPLOY가 없을 때 apply할 manifest 경로
#                  (default: scripts/step04_apply_deployment/nginx-deployment.yaml)
#
# Epoch definition:
# - DOWN_START_EPOCH : scale down 명령 직전 timestamp
# - DOWN_END_EPOCH   : scale down rollout 완료 직후 timestamp
# - UP_START_EPOCH   : scale up 명령 직전 timestamp
# - UP_END_EPOCH     : scale up rollout 완료 직후 timestamp
# - START_EPOCH = DOWN_START_EPOCH
# - READY_EPOCH = DOWN_END_EPOCH (본 step에서는 "down 완료"를 READY로 기록)
# - END_EPOCH   = UP_END_EPOCH
# - T_down  = DOWN_END_EPOCH - DOWN_START_EPOCH
# - T_up    = UP_END_EPOCH   - UP_START_EPOCH
# - T_total = END_EPOCH - START_EPOCH
# - export_csv는 [START_EPOCH, END_EPOCH] 전체 구간을 Netdata API로 5초 평균(group=average, points=ceil(dur/5))으로 export
set -euo pipefail

STEP="step06_scale_up_down"
RUNS="${RUNS:-10}"
DEPLOY="${DEPLOY:-nginx}"
REPLICAS_HIGH="${REPLICAS_HIGH:-3}"
REPLICAS_LOW="${REPLICAS_LOW:-1}"

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

prep_scale() {
  kubectl wait --for=condition=Ready nodes --all --timeout=180s >/dev/null

  if ! kubectl get deploy/"${DEPLOY}" >/dev/null 2>&1; then
    [[ -f "${MANIFEST}" ]] && kubectl apply -f "${MANIFEST}" >/dev/null
  fi

  kubectl scale deploy/"${DEPLOY}" --replicas="${REPLICAS_HIGH}" >/dev/null 2>&1 || true
  kubectl rollout status deploy/"${DEPLOY}" --timeout=300s >/dev/null
}

echo "[${STEP}] RUNS=${RUNS}, down ${REPLICAS_HIGH}->${REPLICAS_LOW}, up ${REPLICAS_LOW}->${REPLICAS_HIGH}"
echo "[${STEP}] charts cpu=${CPU_CHART} ram=${RAM_CHART} disk_util=${DISK_UTIL_CHART} io=${IO_CHART}"

for i in $(seq 1 "${RUNS}"); do
  echo "== [${STEP}] run_${i}/${RUNS} =="

  prep_scale

  RUN_LOG="${LOG_DIR}/run_${i}.log"
  RUN_DATA="${DATA_DIR}/run_${i}"
  mkdir -p "${RUN_DATA}"

  # 1) scale down 3 -> 1
  DOWN_START_EPOCH="$(date +%s)"
  kubectl scale deploy/"${DEPLOY}" --replicas="${REPLICAS_LOW}" >/dev/null
  kubectl rollout status deploy/"${DEPLOY}" --timeout=300s >/dev/null
  DOWN_END_EPOCH="$(date +%s)"

  # 2) scale up 1 -> 3
  UP_START_EPOCH="$(date +%s)"
  kubectl scale deploy/"${DEPLOY}" --replicas="${REPLICAS_HIGH}" >/dev/null
  kubectl rollout status deploy/"${DEPLOY}" --timeout=300s >/dev/null
  UP_END_EPOCH="$(date +%s)"

  START_EPOCH="${DOWN_START_EPOCH}"
  READY_EPOCH="${DOWN_END_EPOCH}"
  END_EPOCH="${UP_END_EPOCH}"

  T_down="$((DOWN_END_EPOCH - DOWN_START_EPOCH))"
  T_up="$((UP_END_EPOCH - UP_START_EPOCH))"
  T_total="$((END_EPOCH - START_EPOCH))"

  cat > "${RUN_LOG}" <<EOL
STEP=${STEP}
RUN=${i}
START_EPOCH=${START_EPOCH}
READY_EPOCH=${READY_EPOCH}
END_EPOCH=${END_EPOCH}
DOWN_START_EPOCH=${DOWN_START_EPOCH}
DOWN_END_EPOCH=${DOWN_END_EPOCH}
UP_START_EPOCH=${UP_START_EPOCH}
UP_END_EPOCH=${UP_END_EPOCH}
T_down=${T_down}
T_up=${T_up}
T_total=${T_total}
EOL

  # Netdata export (전체 구간: DOWN_START ~ UP_END)
  export_csv "${CPU_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_cpu.csv"
  export_csv "${RAM_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_ram.csv"
  export_csv "${DISK_UTIL_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_util_mmcblk0.csv"
  export_csv "${IO_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_io_mmcblk0.csv"
done

python3 "${REPO_ROOT}/analysis/plot_step06.py" --step "${STEP}"
echo "[DONE] ${STEP}"
