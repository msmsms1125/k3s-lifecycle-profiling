# - step09_stop_final_idle: k3s 서비스를 실제로 stop -> stop 직후 WINDOW_SEC 동안의 리소스 하강/정리 구간 관찰
# - Step09는 클러스터를 내리는 작업 -> 기본 (RUNS=1)로 설정
#
# Artifacts (per run):
# - logs/redacted/step09_stop_final_idle/run_<i>.log
#     STEP/RUN/START_EPOCH/END_EPOCH/T_total 기록
# - data/netdata/step09_stop_final_idle/run_<i>/
#     system_cpu.csv
#     system_ram.csv
#     disk_util_mmcblk0.csv (DISK_UTIL_CHART가 유효할 때)
#     disk_io_mmcblk0.csv   (IO_CHART가 유효할 때)
# - results/step09_stop_final_idle/
#     (analysis/plot_step09.py가 생성하는 산출물: fig/stats 등)
#
# Env variables:
# - RUNS          : 반복 횟수 (default: 1)
# - WINDOW_SEC    : k3s stop 직후 관찰 window 길이 (default: 60)
# - NETDATA_URL   : Netdata base URL (default: http://127.0.0.1:19999)
# - DISK_UTIL_CHART : Disk util chart id (default: disk_util.mmcblk0)
# - IO_CHART      : Disk IO chart id (default: system.io)
# - CPU_CHART=system.cpu, RAM_CHART=system.ram
#
# Epoch definition:
# - START_EPOCH : `sudo systemctl stop k3s` 실행 시각 (stop 명령 시점)
# - END_EPOCH   : stop 이후 WINDOW_SEC 관찰이 끝난 시각
# - T_total     : END_EPOCH - START_EPOCH
# - export_csv  : [START_EPOCH, END_EPOCH] 구간을 Netdata API로 5초 평균(group=average, points=ceil(dur/5))으로 export
set -euo pipefail

STEP="step09_stop_final_idle"

# Step09는 k3s를 실제로 내리기 때문에 기본은 반드시 1회만!
RUNS="${RUNS:-1}"
WINDOW_SEC="${WINDOW_SEC:-60}"   # stop 직후 관찰 구간(초) - 기본 60초

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs/redacted/${STEP}"
DATA_DIR="${REPO_ROOT}/data/netdata/${STEP}"
RES_DIR="${REPO_ROOT}/results/${STEP}"

NETDATA_URL="${NETDATA_URL:-http://127.0.0.1:19999}"

mkdir -p "${LOG_DIR}" "${DATA_DIR}" "${RES_DIR}"

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }; }
require_cmd date
require_cmd python3
require_cmd curl
require_cmd systemctl

# netdata chart id (disk util은 환경마다 다르지만 너는 mmcblk0)
CPU_CHART="system.cpu"
RAM_CHART="system.ram"
DISK_UTIL_CHART="${DISK_UTIL_CHART:-disk_util.mmcblk0}"
# disk io는 네 환경에서 system.io가 살아있었음
IO_CHART="${IO_CHART:-system.io}"

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

echo "[${STEP}] RUNS=${RUNS} (default=1), WINDOW_SEC=${WINDOW_SEC}"
echo "[${STEP}] DISK_UTIL_CHART=${DISK_UTIL_CHART}"
echo "[${STEP}] IO_CHART=${IO_CHART}"

for i in $(seq 1 "${RUNS}"); do
  echo "== [${STEP}] run_${i}/${RUNS} =="

  RUN_LOG="${LOG_DIR}/run_${i}.log"
  RUN_DATA="${DATA_DIR}/run_${i}"
  mkdir -p "${RUN_DATA}"

  # start: k3s stop 실행 시각
  START_EPOCH="$(date +%s)"

  # (선택) 워커도 같이 내리려면 아래 SSH 라인 추가해서 사용
  # ssh <worker_user>@<worker_host> "sudo systemctl stop k3s-agent" || true

  sudo systemctl stop k3s || true

  # stop 직후 WINDOW_SEC 동안 관찰(리소스 하강)
  sleep "${WINDOW_SEC}"

  END_EPOCH="$(date +%s)"
  T_TOTAL="$((END_EPOCH - START_EPOCH))"

  cat > "${RUN_LOG}" <<EOL
STEP=${STEP}
RUN=${i}
START_EPOCH=${START_EPOCH}
END_EPOCH=${END_EPOCH}
T_total=${T_TOTAL}
EOL

  # netdata는 k3s랑 무관하게 떠있으니 export 가능해야 정상
  export_csv "${CPU_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_cpu.csv"
  export_csv "${RAM_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/system_ram.csv"

  # disk util
  if curl -sG --max-time 3 "${NETDATA_URL}/api/v1/data" --data-urlencode "chart=${DISK_UTIL_CHART}" >/dev/null 2>&1; then
    export_csv "${DISK_UTIL_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_util_mmcblk0.csv"
  fi

  # disk io(system.io)
  if curl -sG --max-time 3 "${NETDATA_URL}/api/v1/data" --data-urlencode "chart=${IO_CHART}" >/dev/null 2>&1; then
    export_csv "${IO_CHART}" "${START_EPOCH}" "${END_EPOCH}" "${RUN_DATA}/disk_io_mmcblk0.csv"
  fi
done

# 파이썬 1번만 실행(네가 저장해둔 plot_step09.py 기준)
python3 "${REPO_ROOT}/analysis/plot_step09.py" --step "${STEP}"

echo "[DONE] ${STEP}"
