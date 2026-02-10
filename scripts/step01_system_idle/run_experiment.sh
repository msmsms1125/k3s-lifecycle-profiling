# - step01_system_idle: K3s(및 워커의 k3s-agent)를 중지한 상태에서 일정 시간(DURATION_SEC) 동안 시스템 idle baseline 측정
#
# Artifacts (per run):
# - logs/redacted/step01_system_idle/run_<i>.log
#   - STEP/RUN/NETDATA_URL/DURATION_SEC
#   - START_EPOCH / END_EPOCH
# - data/netdata/step01_system_idle/run_<i>/
#   - system_cpu.csv
#   - system_ram.csv
# - results/step01_system_idle/run_<i>/
#   - redacted.log
#
# Env vars:
# - RUNS         : 반복 횟수 (default: 3)
# - DURATION_SEC : 관찰 윈도우 길이 (default: 300)
# - WORKER_HOST  : 워커 노드 SSH 호스트(옵션). 설정 시 원격에서 k3s-agent 중지 시도
# - NETDATA_URL  : Netdata base URL (default: http://127.0.0.1:19999)
#
# Epoch definition:
# - START_EPOCH = date +%s (측정 시작 시각, seconds since epoch)
# - END_EPOCH   = START_EPOCH + DURATION_SEC (측정 종료 시각)
# - export_csv는 [START_EPOCH, END_EPOCH] 구간 Netdata CSV export
set -euo pipefail

RUNS="${RUNS:-3}"
DURATION_SEC="${DURATION_SEC:-300}"
WORKER_HOST="${WORKER_HOST:-}"
NETDATA_URL="${NETDATA_URL:-http://127.0.0.1:19999}"

source scripts/utils/netdata_export.sh

step="step01_system_idle"

stop_cluster() {
  sudo systemctl stop k3s || true
  if [[ -n "$WORKER_HOST" ]]; then
    ssh -o StrictHostKeyChecking=no "$WORKER_HOST" 'sudo systemctl stop k3s-agent || true' || true
  fi
}

for i in $(seq 1 "$RUNS"); do
  echo "=== [$step] run_$i / $RUNS ==="

  run_dir_data="data/netdata/${step}/run_${i}"
  run_dir_res="results/${step}/run_${i}"
  run_log="logs/redacted/${step}/run_${i}.log"

  rm -rf "$run_dir_data" "$run_dir_res" "$run_log"
  mkdir -p "$run_dir_data" "$run_dir_res" "$(dirname "$run_log")"

  {
    echo "STEP=${step}"
    echo "RUN=run_${i}"
    echo "NETDATA_URL=${NETDATA_URL}"
    echo "DURATION_SEC=${DURATION_SEC}"
  } | tee "$run_log"

  echo "[1] stop cluster services" | tee -a "$run_log"
  stop_cluster

  echo "[2] mark start/end epoch" | tee -a "$run_log"
  START_EPOCH=$(date +%s)
  END_EPOCH=$(( START_EPOCH + DURATION_SEC ))
  echo "START_EPOCH=${START_EPOCH}" | tee -a "$run_log"
  echo "END_EPOCH=${END_EPOCH}" | tee -a "$run_log"

  echo "[3] sleep (collect baseline window)" | tee -a "$run_log"
  sleep "$DURATION_SEC"

  echo "[4] export netdata csv" | tee -a "$run_log"
  export_csv "system.cpu" "$START_EPOCH" "$END_EPOCH" "${run_dir_data}/system_cpu.csv" || {
    echo "WARN: failed to export system.cpu" | tee -a "$run_log"
  }
  export_csv "system.ram" "$START_EPOCH" "$END_EPOCH" "${run_dir_data}/system_ram.csv" || {
    echo "WARN: failed to export system.ram" | tee -a "$run_log"
  }

  echo "[5] copy redacted.log into results (git minimum set)" | tee -a "$run_log"
  cp -f "$run_log" "${run_dir_res}/redacted.log"

  echo "[done] run_$i complete"
  echo
done
