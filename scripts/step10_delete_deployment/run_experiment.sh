# - step10_delete_deployment: nginx Deployment를 delete -> 실제로 리소스가 사라질 때까지의 시간 비용과 자원 사용 패턴 측정
# - 각 run마다 nginx 존재를 보장(없으면 manifest apply)한 뒤 delete를 수행, delete 완료 시점까지 Netdata CSV 수집
#
# Artifacts (per run):
# - logs/redacted/step10_delete_deployment/run_<i>.log
#     STEP/RUN/START_EPOCH/END_EPOCH/T_total 기록 (READY_EPOCH/T_ready는 사용하지 않음)
# - data/netdata/step10_delete_deployment/run_<i>/
#     system_cpu.csv
#     system_ram.csv
#     disk_util_mmcblk0.csv
#     disk_io_mmcblk0.csv
# - results/step10_delete_deployment/
#     (analysis/plot_step10.py가 생성하는 산출물: fig/stats 등)
#
# Env variables:
# - RUNS          : 반복 횟수 (default: 10)
# - TIMEOUT_SEC   : delete 완료 대기(폴링) timeout (default: 180)
# - NETDATA_URL   : Netdata base URL (default: http://127.0.0.1:19999)
# - CPU_CHART     : CPU chart id (default: system.cpu)
# - RAM_CHART     : RAM chart id (default: system.ram)
# - DISK_UTIL_CHART : Disk util chart id (default: disk_util.mmcblk0)
# - IO_CHART      : Disk IO chart id (default: system.io)
# - MANIFEST      : nginx가 없을 때 apply할 manifest 경로
#                  (default: scripts/step04_apply_deployment/nginx-deployment.yaml)
#
# Epoch definition:
# - START_EPOCH : `kubectl delete deployment nginx` 실행 직전 timestamp
# - END_EPOCH   : `kubectl get deploy nginx`가 실패(=deployment 없음)하는 첫 시각 (wait_deleted 반환값)
# - T_total     : END_EPOCH - START_EPOCH
# - export_csv  : [START_EPOCH, END_EPOCH] 구간을 Netdata API로 5초 평균(group=average, points=ceil(dur/5))으로 export
set -euo pipefail

STEP="step10_delete_deployment"
RUNS="${RUNS:-10}"
TIMEOUT_SEC="${TIMEOUT_SEC:-180}"

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
require_cmd curl
require_cmd python3
require_cmd kubectl

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

# Step10 전제조건: nginx가 존재해야 delete 의미가 있음.
ensure_nginx_present() {
  if ! kubectl get deploy nginx >/dev/null 2>&1; then
    if [[ -f "${MANIFEST}" ]]; then
      kubectl apply -f "${MANIFEST}" >/dev/null
    else
      echo "[${STEP}] ERROR: nginx manifest not found: ${MANIFEST}" >&2
      exit 1
    fi
  fi
  kubectl rollout status deploy/nginx --timeout="${TIMEOUT_SEC}s" >/dev/null
}

wait_deleted() {
  local deadline=$(( $(date +%s) + TIMEOUT_SEC ))
  while (( $(date +%s) < deadline )); do
    if ! kubectl get deploy nginx >/dev/null 2>&1; then
      # nginx deployment가 없으면 end
      date +%s
      return 0
    fi
    sleep 1
  done
  date +%s
  return 0
}

echo "[${STEP}] RUNS=${RUNS}"
echo "[${STEP}] MANIFEST=${MANIFEST}"
echo "[${STEP}] charts cpu=${CPU_CHART} ram=${RAM_CHART} disk_util=${DISK_UTIL_CHART} io=${IO_CHART}"

# nodes ready 보장
kubectl wait --for=condition=Ready nodes --all --timeout=180s >/dev/null

for i in $(seq 1 "${RUNS}"); do
  echo "== [${STEP}] run_${i}/${RUNS} =="

  ensure_nginx_present

  RUN_LOG="${LOG_DIR}/run_${i}.log"
  RUN_DATA="${DATA_DIR}/run_${i}"
  mkdir -p "${RUN_DATA}"

  START_EPOCH="$(date +%s)"
  kubectl delete deployment nginx --ignore-not-found >/dev/null 2>&1 || true
  END_EPOCH="$(wait_deleted)"
  T_TOTAL="$((END_EPOCH - START_EPOCH))"

  cat > "${RUN_LOG}" <<EOF2
STEP=${STEP}
RUN=${i}
START_EPOCH=${START_EPOCH}
READY_EPOCH=
END_EPOCH=${END_EPOCH}
T_ready=
T_total=${T_TOTAL}
EOF2

  export_csv "${CPU_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_cpu.csv"
  export_csv "${RAM_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_ram.csv"
  export_csv "${DISK_UTIL_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_util_mmcblk0.csv"
  export_csv "${IO_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_io_mmcblk0.csv"
done

python3 "${REPO_ROOT}/analysis/plot_step10.py" --step "${STEP}"
echo "[DONE] ${STEP}"
