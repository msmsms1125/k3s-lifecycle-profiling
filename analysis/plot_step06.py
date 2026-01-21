#!/usr/bin/env python3
import os
import re
import csv
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

# ==========================================
# 경로 설정
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "logs/redacted/step06_scale.log")
OUT_DIR  = os.path.join(BASE_DIR, "results/step06_scale_up_down")

OUT_STATS_CSV = os.path.join(OUT_DIR, "step06_stats.csv")
OUT_GRAPH_PNG = os.path.join(OUT_DIR, "step06_scale_duration.png")

# 정규표현식 (Run 번호와 Duration 추출)
re_dur_up   = re.compile(r"Run\s*(\d+)_Duration_Up\(ms\):\s*(\d+)")
re_dur_down = re.compile(r"Run\s*(\d+)_Duration_Down\(ms\):\s*(\d+)")

def parse_logs():
    if not os.path.exists(LOG_PATH):
        print(f"[ERROR] Log not found: {LOG_PATH}")
        return {}

    runs = {}
    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            
            # Scale Up 시간 추출
            m_up = re_dur_up.search(line)
            if m_up:
                rid = int(m_up.group(1))
                runs.setdefault(rid, {})["up_ms"] = int(m_up.group(2))
            
            # Scale Down 시간 추출
            m_down = re_dur_down.search(line)
            if m_down:
                rid = int(m_down.group(1))
                runs.setdefault(rid, {})["down_ms"] = int(m_down.group(2))

    return runs

def save_stats(runs):
    if not runs: return
    
    with open(OUT_STATS_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run", "scale_up_ms", "scale_down_ms"])
        
        for rid in sorted(runs.keys()):
            d = runs[rid]
            w.writerow([f"run_{rid}", d.get("up_ms", 0), d.get("down_ms", 0)])
            
    print(f"[INFO] Stats saved: {OUT_STATS_CSV}")

def plot_graph(runs):
    if not runs: return

    rids = sorted(runs.keys())
    up_times = [runs[r].get("up_ms", 0) for r in rids]
    down_times = [runs[r].get("down_ms", 0) for r in rids]
    
    x = np.arange(len(rids))
    width = 0.35

    plt.figure(figsize=(10, 6))
    plt.bar(x - width/2, up_times, width, label='Scale Up (1->3)', color='#d62728')
    plt.bar(x + width/2, down_times, width, label='Scale Down (3->1)', color='#1f77b4')

    plt.xlabel('Run')
    plt.ylabel('Duration (ms)')
    plt.title('Step 6: Scale Up vs Down Duration (3 Runs)')
    plt.xticks(x, [f"Run {r}" for r in rids])
    plt.legend()
    plt.grid(axis='y', linestyle='--', alpha=0.5)

    plt.savefig(OUT_GRAPH_PNG)
    print(f"[INFO] Graph saved: {OUT_GRAPH_PNG}")

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    runs = parse_logs()
    if runs:
        save_stats(runs)
        plot_graph(runs)
    else:
        print("[ERROR] No run data found.")

if __name__ == "__main__":
    main()
