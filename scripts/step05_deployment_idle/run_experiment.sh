# - step05_deployment_idle: nginx Deployment가 이미 존재하고 Ready/rollout 완료된 상태를 유지,
#   DURATION_SEC 동안 "deployment idle baseline" 자원 사용 패턴을 측정
# - 매 run마다 READY 시점을 START로 두고(READY_EPOCH==START_EPOCH), 관찰 윈도우 동안 Netdata CSV 수집
#
# Artifacts (per run):
# - logs/redacted/step05_deployment_idle/run_<i>.log
#     STEP/RUN/START_EPOCH/READY_EPOCH/END_EPOCH 및 T_ready/T_total 기록
# - data/netdata/step05_deployment_idle/run_<i>/
#     system_cpu.csv
#     system_ram.csv
#     disk_util_mmcblk0.csv
#     disk_io_mmcblk0.csv   (IO_CHART로 export; 파일명은 disk_io_mmcblk0.csv로 저장)
# - results/step05_deployment_idle/
#     (analysis/plot_step05.py가 생성하는 산출물: fig/stats 등)
#
# Env variables:
# - RUNS         : 반복 횟수 (default: 10)
# - DURATION_SEC : 관찰 윈도우 길이 (default: 300)
# - NETDATA_URL  : Netdata base URL (default: http://127.0.0.1:19999)
# - CPU_CHART    : CPU chart id (default: system.cpu)
# - RAM_CHART    : RAM chart id (default: system.ram)
# - DISK_UTIL_CHART : Disk util chart id (default: disk_util.mmcblk0)
# - IO_CHART     : IO chart id (default: system.io)
# - MANIFEST     : nginx manifest 경로 (default: scripts/step04_apply_deployment/nginx-deployment.yaml)
# - REPLICAS     : nginx replica 수 유지값 (default: 3)
#
# Epoch definition:
# - READY_EPOCH : nginx rollout 완료(ready) 상태를 확인/정렬한 직후 timestamp
# - START_EPOCH : READY_EPOCH와 동일 (T_ready=0으로 정의)
# - END_EPOCH   : START_EPOCH + DURATION_SEC 관찰 후 timestamp
# - T_ready = 0
# - T_total = END_EPOCH - START_EPOCH
# - export_csv는 [START_EPOCH, END_EPOCH] 구간을 Netdata API로 5초 평균(group=average, points=ceil(dur/5))으로 export
set -euo pipefail

STEP="step05_deployment_idle"
RUNS="${RUNS:-10}"
DURATION_SEC="${DURATION_SEC:-300}"

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
REPLICAS="${REPLICAS:-3}"

mkdir -p "${LOG_DIR}" "${DATA_DIR}" "${RES_DIR}"

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }; }
require_cmd date
require_cmd kubectl
require_cmd curl
require_cmd python3

calc_points() {
  local after="$1" before="$2"
  local dur=$((before - after))
  local p=$(( (dur + 4) / 5 ))  # ceil(dur/5)
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

prep_deployment_idle() {
  # 노드 Ready
  kubectl wait --for=condition=Ready nodes --all --timeout=180s >/dev/null

  # nginx 존재 + replicas=3 유지 + rollout 완료
  if [[ -f "${MANIFEST}" ]]; then
    kubectl apply -f "${MANIFEST}" >/dev/null
  fi

  kubectl scale deployment/nginx --replicas="${REPLICAS}" >/dev/null 2>&1 || true

  kubectl rollout status deployment/nginx --timeout=300s >/dev/null
}

echo "[${STEP}] RUNS=${RUNS}, DURATION_SEC=${DURATION_SEC}, REPLICAS=${REPLICAS}"
echo "[${STEP}] MANIFEST=${MANIFEST}"
echo "[${STEP}] CHARTS cpu=${CPU_CHART} ram=${RAM_CHART} disk_util=${DISK_UTIL_CHART} io=${IO_CHART}"

for i in $(seq 1 "${RUNS}"); do
  echo "== [${STEP}] run_${i}/${RUNS} =="

  prep_deployment_idle

  RUN_LOG="${LOG_DIR}/run_${i}.log"
  RUN_DATA="${DATA_DIR}/run_${i}"
  mkdir -p "${RUN_DATA}"

  READY_EPOCH="$(date +%s)"
  START_EPOCH="${READY_EPOCH}"
  sleep "${DURATION_SEC}"
  END_EPOCH="$(date +%s)"

  T_READY=0
  T_TOTAL="$((END_EPOCH - START_EPOCH))"

  cat > "${RUN_LOG}" <<EOL
STEP=${STEP}
RUN=${i}
START_EPOCH=${START_EPOCH}
READY_EPOCH=${READY_EPOCH}
END_EPOCH=${END_EPOCH}
T_ready=${T_READY}
T_total=${T_TOTAL}
EOL

  export_csv "${CPU_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_cpu.csv"
  export_csv "${RAM_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_ram.csv"
  export_csv "${DISK_UTIL_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_util_mmcblk0.csv"

  export_csv "${IO_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_io_mmcblk0.csv"
done

python3 "${REPO_ROOT}/analysis/plot_step05.py" --step "${STEP}"
echo "[DONE] ${STEP}"
