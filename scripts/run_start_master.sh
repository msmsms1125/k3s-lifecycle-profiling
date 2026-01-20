#!/usr/bin/env bash
set -euo pipefail

RUN_ID="start_master_$(date +%Y%m%d_%H%M%S)"
RUN_DIR="data/netdata/${RUN_ID}"
LOG="logs/redacted/${RUN_ID}.log"

mkdir -p "$RUN_DIR" logs/redacted results

START_EPOCH=$(date +%s)
echo "EVENT start_master_start $(date '+%F %T') (epoch=$START_EPOCH)" | tee "$LOG"

sudo systemctl start k3s

echo "WAIT: master Ready..." | tee -a "$LOG"
timeout 300 bash -c 'until sudo k3s kubectl get nodes 2>/dev/null | awk "NR>1{print \$2}" | grep -q Ready; do sleep 1; done'

READY_RC=$?
READY_EPOCH=$(date +%s)
echo "EVENT start_master_ready $(date '+%F %T') (epoch=$READY_EPOCH) rc=$READY_RC" | tee -a "$LOG"

sleep 60
END_EPOCH=$(date +%s)
echo "EVENT start_master_end $(date '+%F %T') (epoch=$END_EPOCH)" | tee -a "$LOG"

echo "RUN_ID=$RUN_ID"
echo "START_EPOCH=$START_EPOCH"
echo "READY_EPOCH=$READY_EPOCH"
echo "END_EPOCH=$END_EPOCH"
