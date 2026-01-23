#!/usr/bin/env python3
import argparse
from pathlib import Path
from typing import Dict, Any, List

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
    return float(np.trapz(y, t))


def pick_ram_used(ram: pd.DataFrame) -> pd.Series:
    if "used" in ram.columns:
        return ram["used"].astype(float)
    cols = [c for c in ram.columns if c not in ("time", "dt")]
    if not cols:
        raise ValueError("RAM csv has no data columns")
    return ram[cols[0]].astype(float)


def read_kv_log(p: Path) -> Dict[str, str]:
    kv = {}
    for line in p.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv


def vline(ax, epoch: int, label: str):
    dt = pd.to_datetime(epoch, unit="s")
    ax.axvline(dt, linestyle="--", linewidth=1)
    ax.text(dt, ax.get_ylim()[1], f" {label}", rotation=90, va="top")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True)
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()

    repo = Path(args.repo_root).resolve()
    step = args.step

    log_dir = repo / "logs" / "redacted" / step
    data_dir = repo / "data" / "netdata" / step
    out_dir = repo / "results" / step
    out_dir.mkdir(parents=True, exist_ok=True)

    run_logs = sorted(log_dir.glob("run_*.log"), key=lambda p: int(p.stem.split("_")[1]))
    rows: List[Dict[str, Any]] = []

    for logp in run_logs:
        kv = read_kv_log(logp)
        run_i = int(kv.get("RUN", logp.stem.split("_")[1]))
        run_name = f"run_{run_i}"

        start = int(kv["START_EPOCH"])
        end = int(kv["END_EPOCH"])
        t_total = float(kv.get("T_total", end - start))

        run_data = data_dir / run_name
        cpu = load_df(run_data / "system_cpu.csv")
        ram = load_df(run_data / "system_ram.csv")

        du_path = run_data / "disk_util_mmcblk0.csv"
        dio_path = run_data / "disk_io_mmcblk0.csv"
        du = load_df(du_path) if du_path.exists() else None
        dio = load_df(dio_path) if dio_path.exists() else None

        cpu_total = cpu["user"].astype(float) + cpu["system"].astype(float) + cpu.get("iowait", 0).astype(float)
        ram_used = pick_ram_used(ram)

        disk_util = None
        if du is not None:
            col = "utilization" if "utilization" in du.columns else [c for c in du.columns if c not in ("time","dt")][0]
            disk_util = du[col].astype(float)

        reads = writes = None
        if dio is not None and "reads" in dio.columns and "writes" in dio.columns:
            reads = dio["reads"].astype(float).abs()
            writes = dio["writes"].astype(float).abs()

        run_out = out_dir / run_name
        run_out.mkdir(parents=True, exist_ok=True)
        (run_out / "redacted.log").write_text(logp.read_text())

        # Fig1: 4줄(한 그림)
        fig, ax = plt.subplots(4, 1, figsize=(12, 8), sharex=True)
        ax[0].plot(cpu["dt"], cpu_total); ax[0].set_ylabel("CPU %")
        ax[1].plot(ram["dt"], ram_used);  ax[1].set_ylabel("RAM used (MB)")

        if du is not None and disk_util is not None:
            ax[2].plot(du["dt"], disk_util); ax[2].set_ylabel("Disk util %")
        else:
            ax[2].text(0.01, 0.5, "Disk util: N/A", transform=ax[2].transAxes)
            ax[2].set_ylabel("Disk util %")

        if dio is not None and reads is not None and writes is not None:
            ax[3].plot(dio["dt"], reads, label="reads")
            ax[3].plot(dio["dt"], writes, label="writes")
            ax[3].legend(loc="upper right")
        else:
            ax[3].text(0.01, 0.5, "IO: N/A", transform=ax[3].transAxes)
        ax[3].set_ylabel("IO (KB/s)")
        ax[3].set_xlabel("time")

        for a in ax:
            vline(a, start, "START")
            vline(a, end, "END")

        fig.suptitle(f"{step} - {run_name}")
        fig.tight_layout()
        fig.savefig(run_out / "fig1_timeseries.png", dpi=200)
        plt.close(fig)

        row: Dict[str, Any] = {
            "step": step,
            "run": run_i,
            "START_EPOCH": start,
            "READY_EPOCH": "",
            "END_EPOCH": end,
            "T_ready": "",
            "T_total": t_total,

            "cpu_mean": float(cpu_total.mean()),
            "cpu_peak": float(cpu_total.max()),
            "cpu_auc":  auc(cpu_total, cpu["dt"]),

            "ram_mean": float(ram_used.mean()),
            "ram_peak": float(ram_used.max()),
            "ram_auc":  auc(ram_used, ram["dt"]),
        }

        if du is not None and disk_util is not None:
            row.update({
                "disk_util_mean": float(disk_util.mean()),
                "disk_util_peak": float(disk_util.max()),
                "disk_util_auc":  auc(disk_util, du["dt"]),
            })
        else:
            row.update({"disk_util_mean": np.nan, "disk_util_peak": np.nan, "disk_util_auc": np.nan})

        if dio is not None and reads is not None and writes is not None:
            row.update({
                "disk_io_read_mean": float(reads.mean()),
                "disk_io_read_peak": float(reads.max()),
                "disk_io_read_auc":  auc(reads, dio["dt"]),
                "disk_io_write_mean": float(writes.mean()),
                "disk_io_write_peak": float(writes.max()),
                "disk_io_write_auc":  auc(writes, dio["dt"]),
            })
        else:
            row.update({
                "disk_io_read_mean": np.nan, "disk_io_read_peak": np.nan, "disk_io_read_auc": np.nan,
                "disk_io_write_mean": np.nan, "disk_io_write_peak": np.nan, "disk_io_write_auc": np.nan,
            })

        pd.DataFrame([row]).to_csv(run_out / "stats.csv", index=False)
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("run")
    df.to_csv(out_dir / "summary.csv", index=False)

    # Fig2 (한 파일 boxplot 묶음)
    cols = ["T_total", "cpu_mean", "cpu_peak", "ram_mean", "ram_peak", "disk_util_mean", "disk_util_peak"]
    cols = [c for c in cols if c in df.columns and df[c].notna().any()]
    if cols:
        fig, axes = plt.subplots(2, int(np.ceil(len(cols)/2)), figsize=(13, 6))
        axes = np.array(axes).reshape(-1)
        for i, c in enumerate(cols):
            axes[i].boxplot(df[c].dropna().to_numpy(), labels=[c])
            axes[i].set_title(c)
        for j in range(i + 1, len(axes)):
            axes[j].axis("off")
        fig.suptitle(f"{step} - Fig2 distribution")
        fig.tight_layout()
        fig.savefig(out_dir / "fig2_distribution.png", dpi=200)
        plt.close(fig)

    print("Saved:", out_dir / "summary.csv")
    if (out_dir / "fig2_distribution.png").exists():
        print("Saved:", out_dir / "fig2_distribution.png")


if __name__ == "__main__":
    main()
