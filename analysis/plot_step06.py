#!/usr/bin/env python3
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List

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


def cut_window(df: pd.DataFrame, start_epoch: int, end_epoch: int) -> pd.DataFrame:
    s = pd.to_datetime(start_epoch, unit="s")
    e = pd.to_datetime(end_epoch, unit="s")
    return df[(df["dt"] >= s) & (df["dt"] <= e)].copy()


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

        ds = int(kv["DOWN_START_EPOCH"])
        de = int(kv["DOWN_END_EPOCH"])
        us = int(kv["UP_START_EPOCH"])
        ue = int(kv["UP_END_EPOCH"])

        t_down = float(kv.get("T_down", de - ds))
        t_up = float(kv.get("T_up", ue - us))
        t_total = float(kv.get("T_total", ue - ds))

        run_data = data_dir / run_name
        cpu = load_df(run_data / "system_cpu.csv")
        ram = load_df(run_data / "system_ram.csv")
        du  = load_df(run_data / "disk_util_mmcblk0.csv") if (run_data / "disk_util_mmcblk0.csv").exists() else None
        dio = load_df(run_data / "disk_io_mmcblk0.csv") if (run_data / "disk_io_mmcblk0.csv").exists() else None

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

        # down/up window cut
        cpu_down = cut_window(pd.DataFrame({"dt": cpu["dt"], "v": cpu_total}), ds, de)
        cpu_up   = cut_window(pd.DataFrame({"dt": cpu["dt"], "v": cpu_total}), us, ue)

        ram_down = cut_window(pd.DataFrame({"dt": ram["dt"], "v": ram_used}), ds, de)
        ram_up   = cut_window(pd.DataFrame({"dt": ram["dt"], "v": ram_used}), us, ue)

        du_down = du_up = None
        if du is not None and disk_util is not None:
            tmp = pd.DataFrame({"dt": du["dt"], "v": disk_util})
            du_down = cut_window(tmp, ds, de)
            du_up   = cut_window(tmp, us, ue)

        dio_r_down = dio_r_up = dio_w_down = dio_w_up = None
        if dio is not None and reads is not None and writes is not None:
            tmp_r = pd.DataFrame({"dt": dio["dt"], "v": reads})
            tmp_w = pd.DataFrame({"dt": dio["dt"], "v": writes})
            dio_r_down = cut_window(tmp_r, ds, de)
            dio_r_up   = cut_window(tmp_r, us, ue)
            dio_w_down = cut_window(tmp_w, ds, de)
            dio_w_up   = cut_window(tmp_w, us, ue)

        run_out = out_dir / run_name
        run_out.mkdir(parents=True, exist_ok=True)
        (run_out / "redacted.log").write_text(logp.read_text())

        # Fig1 (전체)
        fig, ax = plt.subplots(4, 1, figsize=(12, 8), sharex=True)
        ax[0].plot(cpu["dt"], cpu_total); ax[0].set_ylabel("CPU %")
        ax[1].plot(ram["dt"], ram_used);  ax[1].set_ylabel("RAM used (MB)")

        if du is not None and disk_util is not None:
            ax[2].plot(du["dt"], disk_util); ax[2].set_ylabel("Disk util %")
        else:
            ax[2].text(0.01, 0.5, "Disk util: N/A", transform=ax[2].transAxes); ax[2].set_ylabel("Disk util %")

        if dio is not None and reads is not None and writes is not None:
            ax[3].plot(dio["dt"], reads, label="reads")
            ax[3].plot(dio["dt"], writes, label="writes")
            ax[3].legend(loc="upper right")
        else:
            ax[3].text(0.01, 0.5, "IO: N/A", transform=ax[3].transAxes)
        ax[3].set_ylabel("IO (KB/s)")
        ax[3].set_xlabel("time")

        for a in ax:
            vline(a, ds, "DOWN_START")
            vline(a, de, "DOWN_END")
            vline(a, us, "UP_START")
            vline(a, ue, "UP_END")

        fig.suptitle(f"{step} - {run_name}")
        fig.tight_layout()
        fig.savefig(run_out / "fig1_timeseries.png", dpi=200)
        plt.close(fig)

        def stats_block(prefix: str, win: pd.DataFrame) -> Dict[str, Any]:
            if win is None or len(win) == 0:
                return {f"{prefix}_mean": np.nan, f"{prefix}_peak": np.nan, f"{prefix}_auc": np.nan}
            return {
                f"{prefix}_mean": float(win["v"].mean()),
                f"{prefix}_peak": float(win["v"].max()),
                f"{prefix}_auc":  auc(win["v"], win["dt"]),
            }

        row: Dict[str, Any] = {
            "step": step,
            "run": run_i,
            "DOWN_START_EPOCH": ds,
            "DOWN_END_EPOCH": de,
            "UP_START_EPOCH": us,
            "UP_END_EPOCH": ue,
            "T_down": t_down,
            "T_up": t_up,
            "T_total": t_total,
        }

        row.update(stats_block("cpu_down", cpu_down))
        row.update(stats_block("cpu_up", cpu_up))
        row.update(stats_block("ram_down", ram_down))
        row.update(stats_block("ram_up", ram_up))

        row.update(stats_block("disk_util_down", du_down))
        row.update(stats_block("disk_util_up", du_up))

        row.update(stats_block("io_read_down", dio_r_down))
        row.update(stats_block("io_read_up", dio_r_up))
        row.update(stats_block("io_write_down", dio_w_down))
        row.update(stats_block("io_write_up", dio_w_up))

        pd.DataFrame([row]).to_csv(run_out / "stats.csv", index=False)
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("run")
    df.to_csv(out_dir / "summary.csv", index=False)

    # Fig2 distribution (한 파일)
    fig_cols = [
        ("T_down", "T_down"),
        ("T_up", "T_up"),
        ("cpu_down_mean", "cpu_down_mean"),
        ("cpu_up_mean", "cpu_up_mean"),
        ("ram_down_mean", "ram_down_mean"),
        ("ram_up_mean", "ram_up_mean"),
    ]
    avail = [(c, label) for c, label in fig_cols if c in df.columns and df[c].notna().any()]
    n = len(avail)
    if n > 0:
        rows_n = 2
        cols_n = int(np.ceil(n / rows_n))
        fig, axes = plt.subplots(rows_n, cols_n, figsize=(12, 6))
        axes = np.array(axes).reshape(-1)
        for i, (c, label) in enumerate(avail):
            axes[i].boxplot(df[c].dropna().to_numpy(), labels=[label])
            axes[i].set_title(label)
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
