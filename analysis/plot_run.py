#!/usr/bin/env python3
import sys
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

def load_csv(path: Path):
    df = pd.read_csv(path)
    if 'time' in df.columns:
        if pd.api.types.is_numeric_dtype(df['time']):
            df['dt'] = pd.to_datetime(df['time'], unit='s')
        else:
            df['dt'] = pd.to_datetime(df['time'], errors='coerce')
        if df['dt'].isna().any():
            bad = df[df['dt'].isna()].head(3)
            raise ValueError(f"Failed to parse time in {path}: {bad.to_dict(orient='records')}")
    return df

def first_data_col(df):
    cols = [c for c in df.columns if c not in ('time','dt')]
    return cols[0] if cols else None

def main(run_dir: str):
    run_path = Path(run_dir)
    step_name = run_path.parent.name

    cpu_path = run_path / "system_cpu.csv"
    ram_path = run_path / "system_ram.csv"
    util_path = run_path / "disk_util_mmcblk0.csv"
    io_path   = run_path / "disk_io_mmcblk0.csv"

    if not cpu_path.exists() or not ram_path.exists():
        print("Missing CSV files:", cpu_path, ram_path)
        sys.exit(1)

    cpu = load_csv(cpu_path)
    ram = load_csv(ram_path)

    for col in ['user','system','iowait']:
        if col not in cpu.columns:
            print("CPU csv missing:", col, "cols=", list(cpu.columns))
            sys.exit(1)
    cpu['cpu_total'] = cpu['user'] + cpu['system'] + cpu['iowait']

    ram_used_col = 'used' if 'used' in ram.columns else first_data_col(ram)
    if ram_used_col is None:
        print("RAM csv has no data columns:", list(ram.columns))
        sys.exit(1)

    # Optional disk
    disk_util = load_csv(util_path) if util_path.exists() else None
    disk_io   = load_csv(io_path) if io_path.exists() else None

    summary = {
        "run": run_path.name,
        "cpu_avg": float(cpu['cpu_total'].mean()),
        "cpu_peak": float(cpu['cpu_total'].max()),
        "ram_avg": float(ram[ram_used_col].mean()),
        "ram_peak": float(ram[ram_used_col].max()),
        "ram_col": ram_used_col,
    }

    # disk util
    if disk_util is not None:
        util_col = first_data_col(disk_util)
        if util_col:
            summary["disk_util_avg"] = float(disk_util[util_col].mean())
            summary["disk_util_peak"] = float(disk_util[util_col].max())
            summary["disk_util_col"] = util_col

    # disk io (read/write col 찾기)
    if disk_io is not None:
        data_cols = [c for c in disk_io.columns if c not in ('time','dt')]
        read_col = next((c for c in data_cols if 'read' in c.lower()), None)
        write_col = next((c for c in data_cols if 'write' in c.lower()), None)
        if read_col is None and data_cols:
            read_col = data_cols[0]
        if write_col is None and len(data_cols) >= 2:
            write_col = data_cols[1]

        if read_col:
            summary["disk_read_avg"] = float(disk_io[read_col].mean())
            summary["disk_read_peak"] = float(disk_io[read_col].max())
            summary["disk_read_col"] = read_col
        if write_col:
            summary["disk_write_avg"] = float(disk_io[write_col].mean())
            summary["disk_write_peak"] = float(disk_io[write_col].max())
            summary["disk_write_col"] = write_col

    # outputs (기존 방식 유지: plot.png + stats.csv)
    out_dir = Path("results") / step_name / run_path.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = out_dir / "plot.png"
    out_csv = out_dir / "stats.csv"

    plt.figure(figsize=(10,4))
    plt.plot(cpu['dt'], cpu['cpu_total'])
    plt.xlabel("time"); plt.ylabel("CPU % (user+system+iowait)")
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
        sys.exit(1)
    main(sys.argv[1])
