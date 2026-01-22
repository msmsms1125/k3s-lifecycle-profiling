#!/usr/bin/env python3
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def load_df(p: Path) -> pd.DataFrame:
    df = pd.read_csv(p)
    if "time" not in df.columns:
        raise ValueError(f"missing time column: {p}")

    # time이 문자열이면 그대로 파싱, 숫자면 epoch(s)로 파싱
    if pd.api.types.is_numeric_dtype(df["time"]):
        df["dt"] = pd.to_datetime(df["time"], unit="s")
    else:
        df["dt"] = pd.to_datetime(df["time"])

    return df.sort_values("dt")

def auc(series: pd.Series, dt: pd.Series) -> float:
    t = (dt - dt.iloc[0]).dt.total_seconds().to_numpy()
    y = series.to_numpy(dtype=float)
    return float(np.trapz(y, t))

def pick_ram_used(ram: pd.DataFrame) -> pd.Series:
    if "used" in ram.columns:
        return ram["used"].astype(float)
    cols = [c for c in ram.columns if c not in ("time", "dt")]
    if not cols:
        raise ValueError("RAM csv has no data columns")
    return ram[cols[0]].astype(float)

def main(step_dir="data/netdata/step01_system_idle", out_dir="results/step01_system_idle"):
    step = Path(step_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    run_dirs = sorted(
        [p for p in step.iterdir() if p.is_dir() and p.name.startswith("run_")],
        key=lambda x: int(x.name.split("_")[1])
    )

    for run in run_dirs:
        cpu = load_df(run / "system_cpu.csv")
        ram = load_df(run / "system_ram.csv")
        du  = load_df(run / "disk_util_mmcblk0.csv")
        dio = load_df(run / "disk_io_mmcblk0.csv")

        cpu_total = cpu["user"].astype(float) + cpu["system"].astype(float) + cpu.get("iowait", 0).astype(float)
        ram_used  = pick_ram_used(ram)
        disk_util = du["utilization"].astype(float)

        reads  = dio["reads"].astype(float).abs()
        writes = dio["writes"].astype(float).abs()

        run_out = out / run.name
        run_out.mkdir(parents=True, exist_ok=True)

        # Fig1: CPU/RAM/Disk util 3패널
        fig, ax = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
        ax[0].plot(cpu["dt"], cpu_total); ax[0].set_ylabel("CPU % (user+system+iowait)")
        ax[1].plot(ram["dt"], ram_used);  ax[1].set_ylabel("RAM used (MB)")
        ax[2].plot(du["dt"],  disk_util); ax[2].set_ylabel("Disk util %"); ax[2].set_xlabel("time")
        fig.suptitle(f"step01 system idle - {run.name}")
        fig.tight_layout()
        fig.savefig(run_out / "fig1_timeseries_cpu_ram_disk.png", dpi=200)
        plt.close(fig)

        # Fig1-IO: reads/writes
        fig = plt.figure(figsize=(11, 4))
        plt.plot(dio["dt"], reads, label="reads")
        plt.plot(dio["dt"], writes, label="writes")
        plt.xlabel("time"); plt.ylabel("KB/s (abs)"); plt.title(f"step01 system idle - {run.name} - disk IO")
        plt.legend(); plt.tight_layout()
        plt.savefig(run_out / "fig1_timeseries_disk_io.png", dpi=200)
        plt.close(fig)

        rows.append({
            "run": run.name,

            "cpu_mean": float(cpu_total.mean()),
            "cpu_peak": float(cpu_total.max()),
            "cpu_auc":  auc(cpu_total, cpu["dt"]),

            "ram_mean": float(ram_used.mean()),
            "ram_peak": float(ram_used.max()),
            "ram_auc":  auc(ram_used, ram["dt"]),

            "disk_util_mean": float(disk_util.mean()),
            "disk_util_peak": float(disk_util.max()),
            "disk_util_auc":  auc(disk_util, du["dt"]),

            "disk_read_mean": float(reads.mean()),
            "disk_read_peak": float(reads.max()),
            "disk_read_auc":  auc(reads, dio["dt"]),

            "disk_write_mean": float(writes.mean()),
            "disk_write_peak": float(writes.max()),
            "disk_write_auc":  auc(writes, dio["dt"]),
        })

    df = pd.DataFrame(rows)
    df.to_csv(out / "summary_step01.csv", index=False)

    # Fig2: 분포 boxplot (각각 따로)
    def save_box(col: str, title: str, fname: str):
        fig = plt.figure(figsize=(7, 4))
        plt.boxplot(df[col].dropna(), labels=[col])
        plt.title(title); plt.tight_layout()
        plt.savefig(out / fname, dpi=200)
        plt.close(fig)

    save_box("cpu_mean", "Fig2 - CPU mean distribution (step01)", "fig2_cpu_mean_box.png")
    save_box("ram_mean", "Fig2 - RAM used mean distribution (step01)", "fig2_ram_mean_box.png")
    save_box("disk_util_mean", "Fig2 - Disk util mean distribution (step01)", "fig2_disk_util_mean_box.png")

    print("Saved:", out / "summary_step01.csv")
    print("Saved Fig2:", out / "fig2_cpu_mean_box.png", out / "fig2_ram_mean_box.png", out / "fig2_disk_util_mean_box.png")

if __name__ == "__main__":
    main(*sys.argv[1:])
