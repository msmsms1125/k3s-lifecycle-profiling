#!/bin/bash

# [설정] 스크립트 위치 기준으로 경로를 잡습니다.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/../.."
LOG_DIR="$PROJECT_ROOT/logs/redacted"
YAML_FILE="$SCRIPT_DIR/nginx-deployment.yaml"
LOG_FILE="$LOG_DIR/step04_apply_deployment.log"
PYTHON_SCRIPT="$PROJECT_ROOT/analysis/plot_step04.py"
RESULT_DIR="$PROJECT_ROOT/results/step04_apply_deployment"

mkdir -p "$LOG_DIR"
mkdir -p "$RESULT_DIR"

echo "=== [Step 4] Apply Deployment Experiment (3 Runs) Start ===" | tee -a "$LOG_FILE"

# ==========================================
# 반복 실험 시작 (3회)
# ==========================================
for i in {1..3}; do
    echo "" | tee -a "$LOG_FILE"
    echo "----------------------------------------" | tee -a "$LOG_FILE"
    echo "Starting Run #$i..." | tee -a "$LOG_FILE"
    echo "----------------------------------------" | tee -a "$LOG_FILE"

    # 0. 초기화 (Clean Up)
    echo "Cleaning up previous deployment..."
    kubectl delete deployment nginx-deployment --ignore-not-found --wait=true
    sleep 5
    
    # 1. Start Timestamp
    START_TIME=$(date +%s%N)
    echo "Run ${i}_DEPLOY_START: $(date -d @${START_TIME:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

    # 2. Apply
    kubectl apply -f "$YAML_FILE"

    # 3. Wait
    if ! kubectl rollout status deployment/nginx-deployment --timeout=300s; then
        echo "ERROR: Deployment failed in Run #$i!" | tee -a "$LOG_FILE"
        exit 1
    fi

    # 4. End Timestamp
    END_TIME=$(date +%s%N)
    echo "Run ${i}_DEPLOY_END: $(date -d @${END_TIME:0:10} '+%Y-%m-%d %H:%M:%S.%N')" | tee -a "$LOG_FILE"

    DURATION=$(( (END_TIME - START_TIME) / 1000000 ))
    echo "Run ${i}_Duration(ms): $DURATION" | tee -a "$LOG_FILE"

    # 5. Idle (안정화)
    echo "Stabilizing for 300s (Run #$i)..."
    sleep 300
done

echo "All 3 runs completed." | tee -a "$LOG_FILE"

# 6. Python Analysis 실행
echo "Running Python Analysis..." | tee -a "$LOG_FILE"
if [ -f "$PYTHON_SCRIPT" ]; then
    python3 "$PYTHON_SCRIPT" \
      --log_file "$LOG_FILE" \
      --output_dir "$RESULT_DIR"
else
    echo "Warning: Python script not found at $PYTHON_SCRIPT" | tee -a "$LOG_FILE"
fi

echo "Done."
