set -euo pipefail

STEP="step03_cluster_idle"
RUNS="${RUNS:-10}"
DURATION_SEC="${DURATION_SEC:-300}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs/redacted/${STEP}"
DATA_DIR="${REPO_ROOT}/data/netdata/${STEP}"
RES_DIR="${REPO_ROOT}/results/${STEP}"

NETDATA_URL="${NETDATA_URL:-http://127.0.0.1:19999}"

mkdir -p "${LOG_DIR}" "${DATA_DIR}" "${RES_DIR}"

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }; }
require_cmd date
require_cmd python3
require_cmd kubectl
require_cmd curl

prep_cluster_idle() {
  kubectl delete deployment nginx --ignore-not-found >/dev/null 2>&1 || true
  if [[ -f "${REPO_ROOT}/scripts/step04_apply_deployment/nginx-deployment.yaml" ]]; then
    kubectl delete -f "${REPO_ROOT}/scripts/step04_apply_deployment/nginx-deployment.yaml" --ignore-not-found >/dev/null 2>&1 || true
  fi
  kubectl wait --for=condition=Ready nodes --all --timeout=120s >/dev/null
}

CHART_JSON="$(curl -s "${NETDATA_URL}/api/v1/charts")"
CPU_CHART="system.cpu"
RAM_CHART="system.ram"

DISK_UTIL_CHART="$(python3 - <<'PY'
import json,sys,re
obj=json.loads(sys.stdin.read())
charts=obj.get("charts",{})
cand=[k for k in charts.keys() if re.search(r"(disk.*util).*mmcblk0", k)]
print(cand[0] if cand else "")
PY
<<<"${CHART_JSON}")"

DISK_IO_CHART="$(python3 - <<'PY'
import json,sys,re
obj=json.loads(sys.stdin.read())
charts=obj.get("charts",{})
cand=[k for k in charts.keys() if re.search(r"(disk.*io).*mmcblk0", k)]
print(cand[0] if cand else "")
PY
<<<"${CHART_JSON}")"

# 5초 평균
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

  curl -sG "${NETDATA_URL}/api/v1/data" \
    --data-urlencode "chart=${chart}" \
    --data-urlencode "after=${after}" \
    --data-urlencode "before=${before}" \
    --data-urlencode "group=average" \
    --data-urlencode "points=${points}" \
    --data-urlencode "format=csv" \
    --data-urlencode "options=seconds,flip" \
    > "${out}"
}

echo "[${STEP}] RUNS=${RUNS}, DURATION_SEC=${DURATION_SEC}"
echo "[${STEP}] DISK_UTIL_CHART=${DISK_UTIL_CHART:-<not found>}"
echo "[${STEP}] DISK_IO_CHART=${DISK_IO_CHART:-<not found>}"

for i in $(seq 1 "${RUNS}"); do
  echo "== [${STEP}] run_${i}/${RUNS} =="

  prep_cluster_idle

  RUN_LOG="${LOG_DIR}/run_${i}.log"
  RUN_DATA="${DATA_DIR}/run_${i}"
  mkdir -p "${RUN_DATA}"

  START_EPOCH="$(date +%s)"
  sleep "${DURATION_SEC}"
  END_EPOCH="$(date +%s)"
  T_TOTAL="$((END_EPOCH - START_EPOCH))"

  cat > "${RUN_LOG}" <<EOF
STEP=${STEP}
RUN=${i}
START_EPOCH=${START_EPOCH}
END_EPOCH=${END_EPOCH}
T_total=${T_TOTAL}
EOF

  export_csv "${CPU_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_cpu.csv"
  export_csv "${RAM_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_ram.csv"

  # Disk는 발견되면 저장, 못 찾으면 스킵
  if [[ -n "${DISK_UTIL_CHART}" ]]; then
    export_csv "${DISK_UTIL_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_util_mmcblk0.csv"
  fi
  if [[ -n "${DISK_IO_CHART}" ]]; then
    export_csv "${DISK_IO_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_io_mmcblk0.csv"
  fi
done

python3 "${REPO_ROOT}/analysis/plot_step03.py" --step "${STEP}"

echo "[DONE] ${STEP}"
