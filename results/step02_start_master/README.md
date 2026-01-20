# Step 02 - Start master (k3s start)

## Definition
- start: `systemctl start k3s`
- ready: first time master becomes Ready in `kubectl get nodes`
- end: ready + 60s stabilization

## Runs
- run01_20260120_164210
- run02_(planned)
- run03_(planned)

## Files in each run
- redacted.log : timestamps (masked)
- summary.md / stats.csv / plot.png : generated after exporting Netdata CSV and running analysis
