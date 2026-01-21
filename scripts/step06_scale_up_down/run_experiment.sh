#!/bin/bash

# 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 프로젝트 루트: scripts/step06_scale_up_down (2단계) -> ../..
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
LOG_DIR="$PROJECT_ROOT/logs/redacted"
LOG_FILE="$LOG_DIR/step06_scale.log"

# 폴더 생성
mkdir -p "$LOG_DIR"

echo "=== [Step 6] Scale Up/Down (3 Iterations) Start ===" | tee "$LOG_FILE"

# 0. 사전 확인 (Nginx가 떠 있어야 함)
if ! kubectl get deployment nginx-deployment &> /dev/null; then
    echo "[ERROR] nginx-deployment not found! Run Step 4 first." | tee -a "$LOG_FILE"
    exit 1
fi

# 초기 상태 강제 설정 (1개)
echo "Initializing to 1 replica..."
kubectl scale deployment nginx-deployment --replicas=1
kubectl rollout status deployment/nginx-deployment
sleep 5

# ====================================================
# 3회 반복 실험 시작
# ====================================================
for i in {1..3}
do
    echo "" | tee -a "$LOG_FILE"
    echo "=== Run $i Start ===" | tee -a "$LOG_FILE"

    # ---------------------------------------------------------
    # 1. Scale Up (1 -> 3)
    # ---------------------------------------------------------
    echo "Run ${i}: Starting Scale UP (1 -> 3)..." | tee -a "$LOG_FILE"
    
    SCALE_UP_START=$(date +%s%N)
    echo "Run ${i}_SCALE_UP_START: $(date -d @${SCALE_UP_START:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

    kubectl scale deployment nginx-deployment --replicas=3
    
    if ! kubectl rollout status deployment/nginx-deployment --timeout=300s; then
        echo "[ERROR] Run ${i} Scale Up Timed out!" | tee -a "$LOG_FILE"
        exit 1
    fi

    SCALE_UP_END=$(date +%s%N)
    echo "Run ${i}_SCALE_UP_END: $(date -d @${SCALE_UP_END:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"
    
    DURATION_UP=$(( (SCALE_UP_END - SCALE_UP_START) / 1000000 ))
    echo "Run ${i}_Duration_Up(ms): $DURATION_UP" | tee -a "$LOG_FILE"

    # 안정화 (Scale Up 상태 유지)
    echo "Stabilizing for 30s..."
    sleep 30

    # ---------------------------------------------------------
    # 2. Scale Down (3 -> 1)
    # ---------------------------------------------------------
    echo "Run ${i}: Starting Scale DOWN (3 -> 1)..." | tee -a "$LOG_FILE"

    SCALE_DOWN_START=$(date +%s%N)
    echo "Run ${i}_SCALE_DOWN_START: $(date -d @${SCALE_DOWN_START:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

    kubectl scale deployment nginx-deployment --replicas=1

    if ! kubectl rollout status deployment/nginx-deployment --timeout=300s; then
        echo "[ERROR] Run ${i} Scale Down Timed out!" | tee -a "$LOG_FILE"
        exit 1
    fi

    SCALE_DOWN_END=$(date +%s%N)
    echo "Run ${i}_SCALE_DOWN_END: $(date -d @${SCALE_DOWN_END:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

    DURATION_DOWN=$(( (SCALE_DOWN_END - SCALE_DOWN_START) / 1000000 ))
    echo "Run ${i}_Duration_Down(ms): $DURATION_DOWN" | tee -a "$LOG_FILE"

    # 다음 런을 위한 휴식
    echo "Cooldown for 30s..."
    sleep 30
done

echo "=== [Step 6] Experiment Finished ===" | tee -a "$LOG_FILE"
