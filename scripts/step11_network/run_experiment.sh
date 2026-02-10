# - step11_network: master ↔ worker 간 네트워크 지연(ping)과 대역폭(iperf3) 측정
# - 각 run은 WORKERS 목록을 순회하며 (ping → iperf3 → cooldown) 을 수행, 결과 파일로 저장
#
# Artifacts (per run):
# - logs/redacted/step11_network/run_<RUN_IDX>.log
#     STEP/RUN_IDX/START_EPOCH/END_EPOCH/T_total
#     PING_COUNT/PING_INTERVAL/IPERF_DURATION/IPERF_STREAMS/COOLDOWN
#     MASTER_HOST/MASTER_TIME_UTC + WORKERS 목록 기록
# - data/network/step11_network/run_<RUN_IDX>/
#     ping_master_to_<name>.txt
#     iperf_master_to_<name>_tcp.json
#
# Env variables / Params:
# - RUN_IDX: 첫 번째 인자($1)로 받는 run index (필수)
# - PING_COUNT     : ping 패킷 수 (default: 20)
# - PING_INTERVAL  : ping 간격 초 (default: 0.2)
# - IPERF_DURATION : iperf3 측정 시간 초 (default: 10)
# - IPERF_STREAMS  : iperf3 parallel streams(-P) (default: 1)
# - COOLDOWN       : 각 worker 측정 후 cooldown 초 (default: 30)
# - WORKERS        : "name ip" 배열 (각 worker는 iperf3 서버 떠있기)
#
# Epoch definition:
# - START_EPOCH : run 시작 시각 (WORKERS 순회 전)
# - END_EPOCH   : 모든 worker 측정 완료 후 시각
# - T_total     : END_EPOCH - START_EPOCH
set -euo pipefail

PING_COUNT=20
PING_INTERVAL=0.2
IPERF_DURATION=10
IPERF_STREAMS=1
COOLDOWN=30

STEP_NAME="step11_network"

# format: "name ip"
WORKERS=(
  "pi03 100.70.165.30"
  "pi04 100.67.201.85"
  "yhsensorpi 100.117.253.4"
)

RUN_IDX="${1:-}"
if [[ -z "${RUN_IDX}" ]]; then
  echo "Usage: $0 <run_index>"
  exit 1
fi

RUN_DIR_DATA="data/network/${STEP_NAME}/run_${RUN_IDX}"
RUN_LOG="logs/redacted/${STEP_NAME}/run_${RUN_IDX}.log"
mkdir -p "${RUN_DIR_DATA}"
mkdir -p "$(dirname "${RUN_LOG}")"

START_EPOCH="$(date +%s)"
{
  echo "STEP=${STEP_NAME}"
  echo "RUN_IDX=${RUN_IDX}"
  echo "START_EPOCH=${START_EPOCH}"
  echo "PING_COUNT=${PING_COUNT}"
  echo "PING_INTERVAL=${PING_INTERVAL}"
  echo "IPERF_DURATION=${IPERF_DURATION}"
  echo "IPERF_STREAMS=${IPERF_STREAMS}"
  echo "COOLDOWN=${COOLDOWN}"
  echo "MASTER_HOST=$(hostname)"
  echo "MASTER_TIME_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo
  echo "WORKERS:"
  for w in "${WORKERS[@]}"; do
    echo "  ${w}"
  done
  echo
} | tee "${RUN_LOG}"

for w in "${WORKERS[@]}"; do
  name="$(echo "${w}" | awk '{print $1}')"
  ip="$(echo "${w}" | awk '{print $2}')"

  echo "[${name}] ping -> ${ip}" | tee -a "${RUN_LOG}"
  ping -c "${PING_COUNT}" -i "${PING_INTERVAL}" "${ip}" \
    | tee "${RUN_DIR_DATA}/ping_master_to_${name}.txt" >/dev/null

  echo "[${name}] iperf3 tcp -> ${ip}" | tee -a "${RUN_LOG}"
  iperf3 -c "${ip}" -t "${IPERF_DURATION}" -P "${IPERF_STREAMS}" --json \
    | tee "${RUN_DIR_DATA}/iperf_master_to_${name}_tcp.json" >/dev/null

  echo "[${name}] cooldown ${COOLDOWN}s" | tee -a "${RUN_LOG}"
  sleep "${COOLDOWN}"
done

END_EPOCH="$(date +%s)"
T_TOTAL="$(( END_EPOCH - START_EPOCH ))"

{
  echo
  echo "END_EPOCH=${END_EPOCH}"
  echo "T_total=${T_TOTAL}"
} | tee -a "${RUN_LOG}"
