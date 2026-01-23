#!/usr/bin/env python3
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple

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


def parse_run_log(text: str) -> Dict[str, Dict[str, str]]:
    # SEG_A/B/C 블록 파싱
    segs: Dict[str, Dict[str, str]] = {}
    cur = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("SEG_") and "=" in line:
            k, v = line.split("=", 1)
            cur = k.strip()  # e.g., SEG_A
            segs[cur] = {"name": v.strip()}
            continue
        if "=" in line and cur is not None:
            k, v = line.split("=", 1)
            segs[cur][k.strip()] = v.strip()
    return segs


def vline(ax, epoch: int, label: str):
    dt = pd.to_datetime(epoch, unit="s")
    ax.axvline(dt, linestyle="--", linewidth=1)
    ax.text(dt, ax.get_ylim()[1], f" {label}", rotation=90, va="top")


def collect_metrics(seg_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cpu = load_df(seg_dir / "system_cpu.csv")
    ram = load_df(seg_dir / "system_ram.csv")
    du  = load_df(seg_dir / "disk_util_mmcblk0.csv")
    dio = load_df(seg_dir / "disk_io_mmcblk0.csv")
    return cpu, ram, du, dio


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
        run_i = int(logp.stem.split("_")[1])
        run_name = f"run_{run_i}"
        segs = parse_run_log(logp.read_text())

        # segment 폴더들
        segA = data_dir / run_name / "segA_cordon"
        segB = data_dir / run_name / "segB_pending"
        segC = data_dir / run_name / "segC_uncordon"

        # Fig1은 3구간을 한 그림에 "이어붙여" 보여주자: (시간축은 실제 dt 기준이라 자연스럽게 분리됨)
        fig, ax = plt.subplots(4, 1, figsize=(12, 9), sharex=True)

        def plot_one(seg_key: str, seg_dir: Path, start: int, ready: str, end: int, tag: str):
            cpu, ram, du, dio = collect_metrics(seg_dir)
            cpu_total = cpu["user"].astype(float) + cpu["system"].astype(float) + cpu.get("iowait", 0).astype(float)
            ram_used  = pick_ram_used(ram)
            disk_util = du["utilization"].astype(float) if "utilization" in du.columns else du[[c for c in du.columns if c not in ("time","dt")][0]].astype(float)
            reads  = dio["reads"].astype(float).abs() if "reads" in dio.columns else None
            writes = dio["writes"].astype(float).abs() if "writes" in dio.columns else None

            ax[0].plot(cpu["dt"], cpu_total, label=tag)
            ax[1].plot(ram["dt"], ram_used, label=tag)
            ax[2].plot(du["dt"],  disk_util, label=tag)
            if reads is not None and writes is not None:
                ax[3].plot(dio["dt"], reads,  label=f"{tag}:reads")
                ax[3].plot(dio["dt"], writes, label=f"{tag}:writes")

            for a in ax:
                vline(a, start, f"{tag}_START")
                if ready:
                    vline(a, int(ready), f"{tag}_READY")
                vline(a, end,   f"{tag}_END")

            # stats (segment별)
            return {
                f"{tag}_START_EPOCH": start,
                f"{tag}_READY_EPOCH": ready,
                f"{tag}_END_EPOCH": end,
                f"{tag}_T_ready": (int(ready) - start) if ready else "",
                f"{tag}_T_total": (end - start),

                f"{tag}_cpu_mean": float(cpu_total.mean()),
                f"{tag}_cpu_peak": float(cpu_total.max()),
                f"{tag}_cpu_auc":  auc(cpu_total, cpu["dt"]),

                f"{tag}_ram_mean": float(ram_used.mean()),
                f"{tag}_ram_peak": float(ram_used.max()),
                f"{tag}_ram_auc":  auc(ram_used, ram["dt"]),

                f"{tag}_disk_util_mean": float(disk_util.mean()),
                f"{tag}_disk_util_peak": float(disk_util.max()),
                f"{tag}_disk_util_auc":  auc(disk_util, du["dt"]),

                f"{tag}_io_read_mean": float(reads.mean()) if reads is not None else np.nan,
                f"{tag}_io_read_peak": float(reads.max()) if reads is not None else np.nan,
                f"{tag}_io_read_auc":  auc(reads, dio["dt"]) if reads is not None else np.nan,

                f"{tag}_io_write_mean": float(writes.mean()) if writes is not None else np.nan,
                f"{tag}_io_write_peak": float(writes.max()) if writes is not None else np.nan,
                f"{tag}_io_write_auc":  auc(writes, dio["dt"]) if writes is not None else np.nan,
            }

        # seg별 epoch 로드
        def get_epoch(seg_key: str, field: str) -> str:
            return segs.get(seg_key, {}).get(field, "")

        A_start = int(get_epoch("SEG_A", "START_EPOCH"))
        A_end   = int(get_epoch("SEG_A", "END_EPOCH"))

        B_start = int(get_epoch("SEG_B", "START_EPOCH"))
        B_ready = get_epoch("SEG_B", "READY_EPOCH")
        B_end   = int(get_epoch("SEG_B", "END_EPOCH"))

        C_start = int(get_epoch("SEG_C", "START_EPOCH"))
        C_end   = int(get_epoch("SEG_C", "END_EPOCH"))

        row: Dict[str, Any] = {"step": step, "run": run_i}

        row.update(plot_one("SEG_A", segA, A_start, "", B_start-1 if False else A_end, "A_CORDON"))  # end는 A_end
        row.update(plot_one("SEG_B", segB, B_start, B_ready, B_end, "B_PENDING"))
        row.update(plot_one("SEG_C", segC, C_start, "", C_end, "C_UNCORDON"))

        ax[0].set_ylabel("CPU %")
        ax[1].set_ylabel("RAM used (MB)")
        ax[2].set_ylabel("Disk util %")
        ax[3].set_ylabel("IO (KB/s)")
        ax[3].set_xlabel("time")
        for a in ax[:3]:
            a.legend(loc="upper right")
        ax[3].legend(loc="upper right", fontsize=8)

        fig.suptitle(f"{step} - {run_name} (A:cordon window, B:pending, C:uncordon)")
        fig.tight_layout()

        run_out = out_dir / run_name
        run_out.mkdir(parents=True, exist_ok=True)
        fig.savefig(run_out / "fig1_timeseries.png", dpi=200)
        plt.close(fig)

        # redacted copy + stats.csv
        (run_out / "redacted.log").write_text(logp.read_text())
        pd.DataFrame([row]).to_csv(run_out / "stats.csv", index=False)

        rows.append(row)

    df = pd.DataFrame(rows).sort_values("run")
    df.to_csv(out_dir / "summary.csv", index=False)

    # Fig2 distribution (대표 지표 몇 개)
    cols = [c for c in df.columns if c.endswith("_T_total") or c.endswith("_cpu_mean") or c.endswith("_ram_mean")]
    cols = [c for c in cols if df[c].notna().any()]
    if cols:
        n = len(cols)
        r = 2
        c = int(np.ceil(n / r))
        fig, axes = plt.subplots(r, c, figsize=(14, 6))
        axes = np.array(axes).reshape(-1)
        for i, col in enumerate(cols):
            axes[i].boxplot(df[col].dropna().to_numpy(), labels=[col])
            axes[i].set_title(col)
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
