#!/usr/bin/env python3
import os
import re
import csv
from statistics import mean, pstdev
import matplotlib.pyplot as plt

LOG_PATH = "logs/redacted/step04_apply_deployment.log"
OUT_DIR = "results/step04_apply_deployment"
OUT_PNG = os.path.join(OUT_DIR, "step04_apply_deployment_plot.png")
OUT_CSV = os.path.join(OUT_DIR, "step04_apply_deployment_stats.csv")

# 로그 예시에서 잡아낼 패턴들:
# Run 1_DEPLOY_START: ...
# Run 1_DEPLOY_END: ...
# Run 1_Duration(ms): 4493
# Duration(ms): 37945  (단일 1회 측정일 수도 있어서 같이 지원)
re_run_start = re.compile(r"Run\s*(\d+)_DEPLOY_START:\s*(.+)")
re_run_end   = re.compile(r"Run\s*(\d+)_DEPLOY_END:\s*(.+)")
re_run_dur   = re.compile(r"Run\s*(\d+)_Duration\(ms\):\s*(\d+)")
re_single_start = re.compile(r"DEPLOY_START:\s*(.+)")
re_single_end   = re.compile(r"DEPLOY_END:\s*(.+)")
re_single_dur   = re.compile(r"Duration\(ms\):\s*(\d+)")

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    if not os.path.exists(LOG_PATH):
        raise FileNotFoundError(f"Log not found: {LOG_PATH}")

    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # run별 정보
    runs = {}  # run_id -> dict(start,end,duration_ms)
    single = {"start": None, "end": None, "duration_ms": None}

    for line in lines:
        line = line.strip()

        m = re_run_start.search(line)
        if m:
            rid = int(m.group(1))
            runs.setdefault(rid, {})["start"] = m.group(2).strip()
            continue

        m = re_run_end.search(line)
        if m:
            rid = int(m.group(1))
            runs.setdefault(rid, {})["end"] = m.group(2).strip()
            continue

        m = re_run_dur.search(line)
        if m:
            rid = int(m.group(1))
            runs.setdefault(rid, {})["duration_ms"] = int(m.group(2))
            continue

        # 단일 측정도 같이 파싱(있으면 CSV에 포함)
        m = re_single_start.search(line)
        if m and "Run" not in line:
            single["start"] = m.group(1).strip()
            continue

        m = re_single_end.search(line)
        if m and "Run" not in line:
            single["end"] = m.group(1).strip()
            continue

        m = re_single_dur.search(line)
        if m and "Run" not in line:
            # 단일 Duration(ms) 라인이 run duration과 섞일 수 있어서 "Run" 없는 줄만
            single["duration_ms"] = int(m.group(1))
            continue

    # run 데이터 정리
    run_rows = []
    for rid in sorted(runs.keys()):
        d = runs[rid]
        if "duration_ms" in d:
            run_rows.append([
                f"run_{rid}",
                d.get("start", ""),
                d.get("end", ""),
                d["duration_ms"]
            ])

    # 단일 측정이 있으면 추가(있을 때만)
    if single["duration_ms"] is not None:
        run_rows.insert(0, ["single", single.get("start",""), single.get("end",""), single["duration_ms"]])

    if not run_rows:
        raise RuntimeError("No durations found in log. Check log format or file path.")

    # CSV 저장
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["label", "deploy_start", "deploy_end", "duration_ms"])
        w.writerows(run_rows)

        # run_1~run_3만으로 summary 내고 싶으면 single 제외하고 계산
        durations = [row[3] for row in run_rows if str(row[0]).startswith("run_")]
        if durations:
            w.writerow([])
            w.writerow(["summary_for_runs_only", "", "", ""])
            w.writerow(["mean_ms", "", "", f"{mean(durations):.2f}"])
            w.writerow(["pstdev_ms", "", "", f"{pstdev(durations):.2f}"])
            w.writerow(["min_ms", "", "", f"{min(durations)}"])
            w.writerow(["max_ms", "", "", f"{max(durations)}"])

    # Plot 저장(간단: run들만)
    labels = [row[0] for row in run_rows if row[0] != "single"]
    values = [row[3] for row in run_rows if row[0] != "single"]

    plt.figure()
    plt.bar(labels, values)
    plt.title("Step04 Apply Deployment - Duration (ms)")
    plt.xlabel("run")
    plt.ylabel("duration_ms")
    plt.tight_layout()
    plt.savefig(OUT_PNG, dpi=200)
    plt.close()

    print(f"[OK] saved: {OUT_PNG}")
    print(f"[OK] saved: {OUT_CSV}")

if __name__ == "__main__":
    main()

