#!/bin/bash

# ==========================================
# 설정
# ==========================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
LOG_DIR="$PROJECT_ROOT/logs/redacted"
LOG_FILE="$LOG_DIR/step08_cordon_uncordon.log"

# 로그 폴더 생성
mkdir -p "$LOG_DIR"

# 워커 노드 이름 찾기 (master가 아닌 노드 중 첫 번째)
WORKER_NODE=$(kubectl get nodes --no-headers | grep -v "master" | awk '{print $1}' | head -n 1)

if [ -z "$WORKER_NODE" ]; then
    echo "[ERROR] Worker node not found!" | tee -a "$LOG_FILE"
    exit 1
fi

echo "=== [Step 8] Cordon/Uncordon Experiment Start (Node: $WORKER_NODE) ===" | tee "$LOG_FILE"

# 0. 초기화: 파드 1개로 줄이기
echo "Initializing to 1 replica..."
kubectl scale deployment nginx-deployment --replicas=1
kubectl rollout status deployment/nginx-deployment
sleep 5

# ====================================================
# 1. Cordon Worker (스케줄링 제한)
# ====================================================
echo "" | tee -a "$LOG_FILE"
echo "--- Phase 1: Cordon Worker ---" | tee -a "$LOG_FILE"

CORDON_START=$(date +%s%N)
echo "CORDON_START: $(date -d @${CORDON_START:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

kubectl cordon "$WORKER_NODE"

CORDON_END=$(date +%s%N)
echo "CORDON_END: $(date -d @${CORDON_END:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"
echo "Worker node '$WORKER_NODE' is now cordoned." | tee -a "$LOG_FILE"

# 관찰 시간 (60초)
echo "Observing Cordon state for 60s..."
sleep 60

# ====================================================
# 2. Deploy with Cordoned Node (Pending 유도)
# ====================================================
echo "" | tee -a "$LOG_FILE"
echo "--- Phase 2: Scale Up to 3 (Expect Pending) ---" | tee -a "$LOG_FILE"

SCALE_START=$(date +%s%N)
echo "SCALE_START: $(date -d @${SCALE_START:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

# 파드 늘리기 (1 -> 3)
kubectl scale deployment nginx-deployment --replicas=3

# Pending 상태 관찰 (30초 동안 대기하며 상태 확인)
echo "Waiting 30s to observe Pending state..."
sleep 30

# 현재 Pending 상태인 파드 개수 확인
PENDING_COUNT=$(kubectl get pods | grep Pending | wc -l)
echo "Current Pending Pods: $PENDING_COUNT" | tee -a "$LOG_FILE"

# ====================================================
# 3. Uncordon Worker (해제 및 배포 재개)
# ====================================================
echo "" | tee -a "$LOG_FILE"
echo "--- Phase 3: Uncordon Worker (Recovery) ---" | tee -a "$LOG_FILE"

UNCORDON_START=$(date +%s%N)
echo "UNCORDON_START: $(date -d @${UNCORDON_START:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

kubectl uncordon "$WORKER_NODE"

# 파드가 모두 Running이 될 때까지 대기
if ! kubectl rollout status deployment/nginx-deployment --timeout=300s; then
    echo "[ERROR] Pods did not recover!" | tee -a "$LOG_FILE"
    exit 1
fi

RECOVERY_END=$(date +%s%N)
echo "RECOVERY_END: $(date -d @${RECOVERY_END:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

# 4. Duration Calculation
DURATION_PENDING=$(( (UNCORDON_START - SCALE_START) / 1000000 ))
DURATION_RECOVERY=$(( (RECOVERY_END - UNCORDON_START) / 1000000 ))

echo "Duration_Pending_Wait(ms): $DURATION_PENDING" | tee -a "$LOG_FILE"
echo "Duration_Recovery(ms): $DURATION_RECOVERY" | tee -a "$LOG_FILE"

echo "=== [Step 8] Experiment Finished ===" | tee -a "$LOG_FILE"
