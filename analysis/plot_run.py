#!/usr/bin/env python3
import sys
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

def load_csv(path: Path):
    df = pd.read_csv(path)

    # time 컬럼 처리:
    # - epoch(초)면 unit='s'
    # - datetime 문자열이면 자동 파싱
    if 'time' in df.columns:
        if pd.api.types.is_numeric_dtype(df['time']):
            df['dt'] = pd.to_datetime(df['time'], unit='s')
        else:
            df['dt'] = pd.to_datetime(df['time'], errors='coerce')
        if df['dt'].isna().any():
            bad = df[df['dt'].isna()].head(3)
            raise ValueError(f"Failed to parse some time values in {path}: {bad.to_dict(orient='records')}")
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

    # CPU total = user + system + iowait
    for col in ['user', 'system', 'iowait']:
        if col not in cpu.columns:
            print("CPU csv missing column:", col)
            print("Columns:", list(cpu.columns))
            sys.exit(1)
    cpu['cpu_total'] = cpu['user'] + cpu['system'] + cpu['iowait']

    # RAM column 선택
    ram_cols = [c for c in ram.columns if c not in ('time','dt')]
    ram_used_col = 'used' if 'used' in ram_cols else (ram_cols[0] if ram_cols else None)
    if ram_used_col is None:
        print("RAM csv has no data columns. Columns:", list(ram.columns))
        sys.exit(1)

    summary = {
        "run": run_path.name,
        "cpu_avg": float(cpu['cpu_total'].mean()),
        "cpu_peak": float(cpu['cpu_total'].max()),
        "ram_avg": float(ram[ram_used_col].mean()),
        "ram_peak": float(ram[ram_used_col].max()),
        "ram_col": ram_used_col,
    }

    # results 저장 경로를 step/run 구조로
    # run_dir: data/netdata/<step>/run_1 형태를 가정
    step_name = run_path.parent.name
    out_dir = Path("results") / step_name / run_path.name
    out_dir.mkdir(parents=True, exist_ok=True)

    out_png = out_dir / "plot.png"
    out_csv = out_dir / "stats.csv"

    # CPU plot
    plt.figure(figsize=(10,4))
    plt.plot(cpu['dt'], cpu['cpu_total'])
    plt.xlabel("time")
    plt.ylabel("CPU % (user+system+iowait)")
    plt.title(f"CPU - {step_name}/{run_path.name}")
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.close()

    pd.DataFrame([summary]).to_csv(out_csv, index=False)

    print("Saved:", out_png)
    print("Saved:", out_csv)
    print("Summary:", summary)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 analysis/plot_run.py <run_dir>")
        print("Example: python3 analysis/plot_run.py data/netdata/step01_system_idle/run_1")
        sys.exit(1)
    main(sys.argv[1])
