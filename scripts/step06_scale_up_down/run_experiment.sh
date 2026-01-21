#!/bin/bash

# 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/../.."
# 결과는 바로 results에 저장
RESULT_DIR="$PROJECT_ROOT/results/step06_scale_up_down"
LOG_FILE="$RESULT_DIR/step06_scale.log"

# 디렉토리 생성
mkdir -p "$RESULT_DIR"

echo "=== [Step 6] Scale Up/Down Experiment Start ===" | tee -a "$LOG_FILE"

# 0. 사전 확인 (Nginx가 떠 있어야 함)
if ! kubectl get deployment nginx-deployment &> /dev/null; then
    echo "[ERROR] nginx-deployment not found! Run Step 4 first." | tee -a "$LOG_FILE"
    exit 1
fi

# 현재 레플리카 확인 (1개여야 함)
CURRENT_REPLICAS=$(kubectl get deployment nginx-deployment -o=jsonpath='{.spec.replicas}')
if [ "$CURRENT_REPLICAS" -ne 1 ]; then
    echo "[WARN] Replicas is $CURRENT_REPLICAS. Resetting to 1..." | tee -a "$LOG_FILE"
    kubectl scale deployment nginx-deployment --replicas=1
    kubectl rollout status deployment/nginx-deployment
    sleep 5
fi

# ---------------------------------------------------------
# 1. Scale Up (1 -> 3)
# ---------------------------------------------------------
echo "----------------------------------------" | tee -a "$LOG_FILE"
echo "Starting Scale UP (1 -> 3)..." | tee -a "$LOG_FILE"

SCALE_UP_START=$(date +%s%N)
echo "SCALE_UP_START: $(date -d @${SCALE_UP_START:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

# 명령 실행
kubectl scale deployment nginx-deployment --replicas=3

# 대기
if ! kubectl rollout status deployment/nginx-deployment --timeout=300s; then
    echo "[ERROR] Scale Up Timed out!" | tee -a "$LOG_FILE"
    exit 1
fi

SCALE_UP_END=$(date +%s%N)
echo "SCALE_UP_END: $(date -d @${SCALE_UP_END:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

DURATION_UP=$(( (SCALE_UP_END - SCALE_UP_START) / 1000000 ))
echo "Duration_ScaleUp(ms): $DURATION_UP" | tee -a "$LOG_FILE"

# 안정화 (Scale Up 상태 유지)
echo "Stabilizing for 60s (3 Replicas)..."
sleep 60

# ---------------------------------------------------------
# 2. Scale Down (3 -> 1)
# ---------------------------------------------------------
echo "----------------------------------------" | tee -a "$LOG_FILE"
echo "Starting Scale DOWN (3 -> 1)..." | tee -a "$LOG_FILE"

SCALE_DOWN_START=$(date +%s%N)
echo "SCALE_DOWN_START: $(date -d @${SCALE_DOWN_START:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

# 명령 실행
kubectl scale deployment nginx-deployment --replicas=1

# 대기
if ! kubectl rollout status deployment/nginx-deployment --timeout=300s; then
    echo "[ERROR] Scale Down Timed out!" | tee -a "$LOG_FILE"
    exit 1
fi

SCALE_DOWN_END=$(date +%s%N)
echo "SCALE_DOWN_END: $(date -d @${SCALE_DOWN_END:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

DURATION_DOWN=$(( (SCALE_DOWN_END - SCALE_DOWN_START) / 1000000 ))
echo "Duration_ScaleDown(ms): $DURATION_DOWN" | tee -a "$LOG_FILE"

# 종료 안정화
echo "Cooldown for 60s (1 Replica)..."
sleep 60

echo "=== [Step 6] Experiment Finished ===" | tee -a "$LOG_FILE"
