#!/usr/bin/env python3
from typing import Optional
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def load_df(p: Path) -> pd.DataFrame:
    df = pd.read_csv(p)
    if "time" not in df.columns:
        raise ValueError(f"missing time column: {p}")
    if pd.api.types.is_numeric_dtype(df["time"]):
        df["dt"] = pd.to_datetime(df["time"], unit="s")
    else:
        df["dt"] = pd.to_datetime(df["time"])
    return df.sort_values("dt")

def auc(series: pd.Series, dt: pd.Series) -> float:
    t = (dt - dt.iloc[0]).dt.total_seconds().to_numpy()
    y = series.to_numpy(dtype=float)
    if len(t) < 2:
        return float("nan")
    return float(np.trapz(y, t))

def pick_first_numeric(df: pd.DataFrame, prefer: Optional[str] = None) -> pd.Series:
    if prefer and prefer in df.columns:
        return df[prefer].astype(float)
    cols = [c for c in df.columns if c not in ("time", "dt")]
    if not cols:
        raise ValueError("csv has no data columns")
    return df[cols[0]].astype(float)

def read_kv_log(p: Path) -> dict:
    d = {}
    for line in p.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d

def add_markers(ax, start_dt, ready_dt, end_dt):
    ax.axvline(start_dt, linestyle="--")
    if ready_dt is not None:
        ax.axvline(ready_dt, linestyle="--")
    ax.axvline(end_dt, linestyle="--")

def main(step: str):
    repo = Path(__file__).resolve().parents[1]
    step_name = step
    log_dir = repo / "logs" / "redacted" / step_name
    data_dir = repo / "data" / "netdata" / step_name
    out_dir = repo / "results" / step_name
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    run_dirs = sorted([p for p in data_dir.iterdir() if p.is_dir() and p.name.startswith("run_")],
                      key=lambda x: int(x.name.split("_")[1]))

    for run in run_dirs:
        run_id = run.name  # run_1
        i = int(run_id.split("_")[1])
        run_out = out_dir / run_id
        run_out.mkdir(parents=True, exist_ok=True)

        # log
        log_path = log_dir / f"{run_id}.log"
        meta = read_kv_log(log_path)
        start_epoch = int(meta["START_EPOCH"])
        ready_epoch = int(meta.get("READY_EPOCH", "") or 0) if "READY_EPOCH" in meta else None
        end_epoch = int(meta["END_EPOCH"])
        t_ready = float(meta.get("T_ready", "nan")) if "T_ready" in meta else float("nan")
        t_total = float(meta.get("T_total", "nan")) if "T_total" in meta else float("nan")

        start_dt = pd.to_datetime(start_epoch, unit="s")
        end_dt = pd.to_datetime(end_epoch, unit="s")
        ready_dt = pd.to_datetime(ready_epoch, unit="s") if ready_epoch else None

        # csv
        cpu = load_df(run / "system_cpu.csv")
        ram = load_df(run / "system_ram.csv")
        du  = load_df(run / "disk_util_mmcblk0.csv") if (run / "disk_util_mmcblk0.csv").exists() and (run / "disk_util_mmcblk0.csv").stat().st_size > 0 else None
        dio = load_df(run / "disk_io_mmcblk0.csv") if (run / "disk_io_mmcblk0.csv").exists() and (run / "disk_io_mmcblk0.csv").stat().st_size > 0 else None

        cpu_total = cpu["user"].astype(float) + cpu["system"].astype(float) + cpu.get("iowait", 0).astype(float)
        ram_used = pick_first_numeric(ram, prefer="used")

        disk_util = None
        if du is not None:
            disk_util = pick_first_numeric(du, prefer="utilization")

        io_read = io_write = None
        if dio is not None:
            # 어떤 컬럼명이든 있으면 첫 2개를 read/write로 취급(없으면 스킵)
            cols = [c for c in dio.columns if c not in ("time", "dt")]
            if len(cols) >= 1:
                io_read = dio[cols[0]].astype(float).abs()
            if len(cols) >= 2:
                io_write = dio[cols[1]].astype(float).abs()

        # ---- fig1 (one figure) ----
        panels = 3 + (1 if (io_read is not None or io_write is not None) else 0)
        fig, ax = plt.subplots(panels, 1, figsize=(12, 8), sharex=True)

        ax[0].plot(cpu["dt"], cpu_total); ax[0].set_ylabel("CPU %")
        add_markers(ax[0], start_dt, ready_dt, end_dt)

        ax[1].plot(ram["dt"], ram_used); ax[1].set_ylabel("RAM")
        add_markers(ax[1], start_dt, ready_dt, end_dt)

        if disk_util is not None:
            ax[2].plot(du["dt"], disk_util); ax[2].set_ylabel("Disk util %")
        else:
            ax[2].text(0.02, 0.6, "Disk util: N/A", transform=ax[2].transAxes)
            ax[2].set_ylabel("Disk util %")
        add_markers(ax[2], start_dt, ready_dt, end_dt)

        if panels == 4:
            idx = 3
            if io_read is not None:
                ax[idx].plot(dio["dt"], io_read, label="io_read")
            if io_write is not None:
                ax[idx].plot(dio["dt"], io_write, label="io_write")
            ax[idx].set_ylabel("Disk IO")
            ax[idx].legend()
            add_markers(ax[idx], start_dt, ready_dt, end_dt)

        ax[-1].set_xlabel("time")
        fig.suptitle(f"{step_name} - {run_id}")
        fig.tight_layout()
        fig.savefig(run_out / "fig1_timeseries.png", dpi=200)
        plt.close(fig)

        # ---- stats row ----
        row = {
            "step": step_name,
            "run": i,
            "START_EPOCH": start_epoch,
            "READY_EPOCH": int(ready_epoch) if ready_epoch else "",
            "END_EPOCH": end_epoch,
            "T_ready": t_ready,
            "T_total": t_total,

            "cpu_mean": float(cpu_total.mean()),
            "cpu_peak": float(cpu_total.max()),
            "cpu_auc": auc(cpu_total, cpu["dt"]),

            "ram_mean": float(ram_used.mean()),
            "ram_peak": float(ram_used.max()),
            "ram_auc": auc(ram_used, ram["dt"]),
        }

        if disk_util is not None:
            row.update({
                "disk_util_mean": float(disk_util.mean()),
                "disk_util_peak": float(disk_util.max()),
                "disk_util_auc": auc(disk_util, du["dt"]),
            })
        else:
            row.update({"disk_util_mean": np.nan, "disk_util_peak": np.nan, "disk_util_auc": np.nan})

        if io_read is not None:
            row.update({
                "disk_io_read_mean": float(io_read.mean()),
                "disk_io_read_peak": float(io_read.max()),
                "disk_io_read_auc": auc(io_read, dio["dt"]),
            })
        else:
            row.update({"disk_io_read_mean": np.nan, "disk_io_read_peak": np.nan, "disk_io_read_auc": np.nan})

        if io_write is not None:
            row.update({
                "disk_io_write_mean": float(io_write.mean()),
                "disk_io_write_peak": float(io_write.max()),
                "disk_io_write_auc": auc(io_write, dio["dt"]),
            })
        else:
            row.update({"disk_io_write_mean": np.nan, "disk_io_write_peak": np.nan, "disk_io_write_auc": np.nan})

        # per-run stats.csv + redacted.log copy
        pd.DataFrame([row]).to_csv(run_out / "stats.csv", index=False)
        (run_out / "redacted.log").write_text(log_path.read_text())

        rows.append(row)

    df = pd.DataFrame(rows).sort_values("run")
    df.to_csv(out_dir / "summary.csv", index=False)

    # fig2_distribution (>=10 runs)
    if len(df) >= 10:
        cols = [c for c in ["T_total", "cpu_mean", "cpu_peak", "cpu_auc", "ram_mean", "disk_util_mean"] if c in df.columns]
        fig = plt.figure(figsize=(12, 7))
        n = len(cols)
        r = 2
        c = (n + 1) // 2
        for idx, col in enumerate(cols, 1):
            ax = fig.add_subplot(r, c, idx)
            ax.boxplot(df[col].dropna(), labels=[col])
            ax.set_title(col)
        fig.tight_layout()
        fig.savefig(out_dir / "fig2_distribution.png", dpi=200)
        plt.close(fig)

    print("Saved:", out_dir / "summary.csv")
    if len(df) >= 10:
        print("Saved:", out_dir / "fig2_distribution.png")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True)
    args = ap.parse_args()
    main(args.step)
