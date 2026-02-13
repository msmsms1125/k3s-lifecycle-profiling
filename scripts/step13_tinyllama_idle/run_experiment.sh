#!/bin/bash
# Step 13: Deployment idle (TinyLlama) 300s
# Description: Measures baseline resource usage for 300s while the model is loaded but idle.

RUN_NUM=$1
DURATION=300
STABILIZATION=15
LOG_DIR="../../logs/redacted/step13_tinyllama_idle"
RESULT_DIR="../../results/step13_tinyllama_idle/run_${RUN_NUM}"

mkdir -p "$RESULT_DIR"

echo "[Step 13] Run $RUN_NUM: Starting TinyLlama Idle Experiment..."

echo "[Step 13] Waiting ${STABILIZATION}s for resource stabilization..."
sleep $STABILIZATION

START_TIME=$(date +%s)
echo "[Step 13] Measurement started at $(date -d @$START_TIME '+%Y-%m-%d %H:%M:%S')"

echo "[Step 13] Sleeping for ${DURATION}s (Idle state)..."
sleep $DURATION

END_TIME=$(date +%s)
echo "[Step 13] Measurement ended at $(date -d @$END_TIME '+%Y-%m-%d %H:%M:%S')"

export START_TIMESTAMP=$START_TIME
export END_TIMESTAMP=$END_TIME
export OUTPUT_DIR=$RESULT_DIR

# Assuming netdata_export.sh exists in utils and handles CSV export based on timestamps
if [ -f "../utils/netdata_export.sh" ]; then
    ../utils/netdata_export.sh "$OUTPUT_DIR" "$START_TIMESTAMP" "$END_TIMESTAMP"
else
    echo "Warning: ../utils/netdata_export.sh not found. Please verify data export path."
fi

echo "Run $RUN_NUM Completed. Duration: ${DURATION}s" > "$LOG_DIR/run_${RUN_NUM}.log"
