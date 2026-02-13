# 시간 확인
print_kst() {
    TZ='Asia/Seoul' date '+%Y-%m-%d %H:%M:%S KST'
}

echo "=================================================="
echo "Step 13: TinyLlama Idle Experiment (10 runs)"
echo "Start Time: $(print_kst)"
echo "=================================================="

chmod +x ./run_experiment.sh

for i in {1..10}
do
    echo "--------------------------------------------------"
    echo "Starting Run #$i at $(print_kst)"
    ./run_experiment.sh $i
    echo "Finished Run #$i at $(print_kst)"
    echo "--------------------------------------------------"
    sleep 5
done

echo "=================================================="
echo "All runs completed successfully."
echo "End Time: $(print_kst)"
echo "=================================================="
