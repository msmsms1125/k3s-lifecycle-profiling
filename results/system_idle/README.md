# System idle (k3s OFF baseline)

## Goal
Measure baseline resource usage when K3s is stopped (cluster OFF).

## Run list
- system_idle_20260119_215622

## What each file means
- *_summary.md
  - Scenario description
  - Measurement window (START_EPOCH ~ END_EPOCH)
  - Export source (Netdata API)

- *_stats.csv
  - cpu_avg : average CPU utilization (%) during the window
  - cpu_peak: peak CPU utilization (%) during the window
  - ram_avg : average RAM used (MiB) during the window
  - ram_peak: peak RAM used (MiB) during the window
  - ram_col : which Netdata column was used (e.g., used)

- *_plot.png
  - CPU time series (cpu_total = user + system + iowait)
  - RAM time series (ram_col, usually "used")
