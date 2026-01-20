#!/usr/bin/env python3
import sys
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

def load_csv(path: Path):
    df = pd.read_csv(path)
    # 첫 컬럼이 time(epoch)일 때 datetime으로 변환
    if 'time' in df.columns:
        df['dt'] = pd.to_datetime(df['time'], unit='s')
    return df

def main(run_dir: str):
    run_path = Path(run_dir)
    cpu_path = run_path / "system_cpu.csv"
    ram_path = run_path / "system_ram.csv"

    if not cpu_path.exists() or not ram_path.exists():
        print("Missing CSV files in:", run_path)
        print("Need:", cpu_path, "and", ram_path)
        sys.exit(1)

    cpu = load_csv(cpu_path)
    ram = load_csv(ram_path)

    # CPU total = user + system + iowait (보수적으로)
    for col in ['user', 'system', 'iowait']:
        if col not in cpu.columns:
            print("CPU csv missing column:", col)
            print("Columns:", list(cpu.columns))
            sys.exit(1)
    cpu['cpu_total'] = cpu['user'] + cpu['system'] + cpu['iowait']

    # RAM은 netdata chart에 따라 컬럼명이 다를 수 있어: "used"가 있으면 그걸 우선
    ram_cols = [c for c in ram.columns if c not in ('time','dt')]
    ram_used_col = 'used' if 'used' in ram_cols else (ram_cols[0] if ram_cols else None)
    if ram_used_col is None:
        print("RAM csv has no data columns. Columns:", list(ram.columns))
        sys.exit(1)

    # 요약 통계
    summary = {
        "run": run_path.name,
        "cpu_avg": float(cpu['cpu_total'].mean()),
        "cpu_peak": float(cpu['cpu_total'].max()),
        "ram_avg": float(ram[ram_used_col].mean()),
        "ram_peak": float(ram[ram_used_col].max()),
        "ram_col": ram_used_col,
    }

    # 출력 파일
    out_png = Path("results") / f"{run_path.name}_plot.png"
    out_csv = Path("results") / f"{run_path.name}_stats.csv"

    # 그래프: CPU
    plt.figure(figsize=(10,4))
    plt.plot(cpu['dt'], cpu['cpu_total'])
    plt.xlabel("time")
    plt.ylabel("CPU % (user+system+iowait)")
    plt.title(f"CPU - {run_path.name}")
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.close()

    # 통계 csv 저장
    pd.DataFrame([summary]).to_csv(out_csv, index=False)

    print("Saved:", out_png)
    print("Saved:", out_csv)
    print("Summary:", summary)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 analysis/plot_run.py <run_dir>")
        print("Example: python3 analysis/plot_run.py data/netdata/system_idle_20260119_215622")
        sys.exit(1)
    main(sys.argv[1])
