#!/bin/bash

# ==========================================
# 설정
# ==========================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 프로젝트 루트: scripts/step07... (2단계) -> ../..
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
LOG_DIR="$PROJECT_ROOT/logs/redacted"
LOG_FILE="$LOG_DIR/step07_rollout_restart.log"

# 로그 폴더 생성
mkdir -p "$LOG_DIR"

echo "=== [Step 7] Rollout Restart (3 Iterations) Start ===" | tee "$LOG_FILE"

# 0. 사전 확인
if ! kubectl get deployment nginx-deployment &> /dev/null; then
    echo "[ERROR] nginx-deployment not found! Run Step 4 first." | tee -a "$LOG_FILE"
    exit 1
fi

# 초기 상태 확인 (Replicas가 1개인지 3개인지? Step 6 끝났으면 1개일 것임)
# 공정한 테스트를 위해 3개로 맞추고 시작할까요? 아니면 1개? 
# 보통 운영 환경은 다중 파드이므로 3개로 맞추고 테스트하겠습니다.
echo "Initializing to 3 replicas for Rolling Update test..."
kubectl scale deployment nginx-deployment --replicas=3
kubectl rollout status deployment/nginx-deployment
sleep 10

# ====================================================
# 3회 반복 실험 시작
# ====================================================
for i in {1..3}
do
    echo "" | tee -a "$LOG_FILE"
    echo "=== Run $i Start ===" | tee -a "$LOG_FILE"

    # 1. Start Log
    RESTART_START=$(date +%s%N)
    echo "Run ${i}_RESTART_START: $(date -d @${RESTART_START:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

    # 2. Command Execution (재배포 명령)
    echo "Executing: kubectl rollout restart deployment/nginx-deployment" | tee -a "$LOG_FILE"
    kubectl rollout restart deployment/nginx-deployment

    # 3. Wait for Rollout (완료 대기)
    if ! kubectl rollout status deployment/nginx-deployment --timeout=300s; then
        echo "[ERROR] Run ${i} Timed out!" | tee -a "$LOG_FILE"
        exit 1
    fi

    # 4. End Log
    RESTART_END=$(date +%s%N)
    echo "Run ${i}_RESTART_END: $(date -d @${RESTART_END:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

    # 5. Duration Calculation
    DURATION=$(( (RESTART_END - RESTART_START) / 1000000 ))
    echo "Run ${i}_Duration(ms): $DURATION" | tee -a "$LOG_FILE"

    # 6. Cooldown (다음 런을 위해 대기)
    echo "Cooldown for 30s..."
    sleep 30
done

echo "=== [Step 7] Experiment Finished ===" | tee -a "$LOG_FILE"
