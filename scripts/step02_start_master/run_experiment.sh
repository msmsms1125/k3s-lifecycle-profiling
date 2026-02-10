set -euo pipefail

RUNS="${RUNS:-10}"
PRE_SEC="${PRE_SEC:-10}"
POST_SEC="${POST_SEC:-30}"

WORKER_HOST="${WORKER_HOST:-}"

NETDATA_URL="${NETDATA_URL:-http://127.0.0.1:19999}"

DISK_DEV="${DISK_DEV:-mmcblk0}"

READY_TIMEOUT_SEC="${READY_TIMEOUT_SEC:-180}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${ROOT_DIR}/scripts/utils/netdata_export.sh"

step="step02_start_master"

stop_cluster() {
  sudo systemctl stop k3s || true
  if [[ -n "$WORKER_HOST" ]]; then
    ssh -o StrictHostKeyChecking=no "$WORKER_HOST" 'sudo systemctl stop k3s-agent || true' || true
  fi
}

wait_master_ready() {
  local deadline="$(( $(date +%s) + READY_TIMEOUT_SEC ))"

  while (( $(date +%s) < deadline )); do
    # service active?
    if ! systemctl is-active --quiet k3s; then
      sleep 1
      continue
    fi

    if sudo k3s kubectl get nodes --no-headers >/dev/null 2>&1; then
      if sudo k3s kubectl get nodes --no-headers 2>/dev/null | grep -q ' Ready '; then
        return 0
      fi
    fi

    sleep 1
  done

  return 1
}

for i in $(seq 1 "$RUNS"); do
  echo "=== [$step] run_${i} / $RUNS ==="

  run_dir_data="${ROOT_DIR}/data/netdata/${step}/run_${i}"
  run_dir_res="${ROOT_DIR}/results/${step}/run_${i}"
  run_log="${ROOT_DIR}/logs/redacted/${step}/run_${i}.log"

  rm -rf "$run_dir_data" "$run_dir_res" "$run_log"
  mkdir -p "$run_dir_data" "$run_dir_res" "$(dirname "$run_log")"

  {
    echo "STEP=${step}"
    echo "RUN=run_${i}"
    echo "NETDATA_URL=${NETDATA_URL}"
    echo "PRE_SEC=${PRE_SEC}"
    echo "POST_SEC=${POST_SEC}"
    echo "DISK_DEV=${DISK_DEV}"
    echo "READY_TIMEOUT_SEC=${READY_TIMEOUT_SEC}"
  } | tee "$run_log"

  echo "[1] stop cluster services" | tee -a "$run_log"
  stop_cluster

  echo "[2] start master + mark START_EPOCH" | tee -a "$run_log"
  START_EPOCH="$(date +%s)"
  echo "START_EPOCH=${START_EPOCH}" | tee -a "$run_log"

  sudo systemctl start k3s | tee -a "$run_log" || true

  echo "[3] wait master READY + mark READY_EPOCH" | tee -a "$run_log"
  if wait_master_ready; then
    READY_EPOCH="$(date +%s)"
    echo "READY_EPOCH=${READY_EPOCH}" | tee -a "$run_log"
  else
    echo "ERROR: master not READY within ${READY_TIMEOUT_SEC}s" | tee -a "$run_log"
    exit 1
  fi

  echo "[4] mark END_EPOCH (= READY + POST_SEC), sleep POST window" | tee -a "$run_log"
  END_EPOCH="$(( READY_EPOCH + POST_SEC ))"
  echo "END_EPOCH=${END_EPOCH}" | tee -a "$run_log"
  sleep "$POST_SEC"

  EXPORT_START="$(( START_EPOCH - PRE_SEC ))"
  if (( EXPORT_START < 0 )); then EXPORT_START=0; fi

  echo "[5] export netdata csv (5s avg) from EXPORT_START..END_EPOCH" | tee -a "$run_log"
  echo "EXPORT_START_EPOCH=${EXPORT_START}" | tee -a "$run_log"

  export_csv "system.cpu"             "$EXPORT_START" "$END_EPOCH" "${run_dir_data}/system_cpu.csv"
  export_csv "system.ram"             "$EXPORT_START" "$END_EPOCH" "${run_dir_data}/system_ram.csv"
  export_csv "disk_util.${DISK_DEV}"  "$EXPORT_START" "$END_EPOCH" "${run_dir_data}/disk_util_${DISK_DEV}.csv"
  export_csv "disk.${DISK_DEV}"       "$EXPORT_START" "$END_EPOCH" "${run_dir_data}/disk_io_${DISK_DEV}.csv"

  echo "[6] write durations + copy redacted.log into results" | tee -a "$run_log"
  echo "T_READY_SEC=$(( READY_EPOCH - START_EPOCH ))" | tee -a "$run_log"
  echo "T_TOTAL_SEC=$(( END_EPOCH - START_EPOCH ))" | tee -a "$run_log"
  cp "$run_log" "${run_dir_res}/redacted.log"

  echo "[done] run_${i} complete" | tee -a "$run_log"
  echo
done
