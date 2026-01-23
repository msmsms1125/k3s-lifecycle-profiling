#!/usr/bin/env python3
import argparse
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def parse_kv_log(p: Path) -> dict:
    kv = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip()
    return kv

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

def pick_ram_used(ram: pd.DataFrame) -> pd.Series:
    if "used" in ram.columns:
        return ram["used"].astype(float)
    cols = [c for c in ram.columns if c not in ("time", "dt")]
    if not cols:
        raise ValueError("RAM csv has no data columns")
    return ram[cols[0]].astype(float)

def safe_get(df: pd.DataFrame, col: str, default=0.0) -> pd.Series:
    if col in df.columns:
        return df[col].astype(float)
    return pd.Series([default] * len(df), index=df.index, dtype=float)

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True)  # e.g., step03_cluster_idle
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    step = args.step

    data_root = repo / "data" / "netdata" / step
    log_root  = repo / "logs" / "redacted" / step
    out_root  = repo / "results" / step
    ensure_dir(out_root)

    run_dirs = sorted([p for p in data_root.glob("run_*") if p.is_dir()],
                      key=lambda x: int(x.name.split("_")[1]))

    all_rows = []

    for run in run_dirs:
        run_id = run.name  # run_1 ...
        run_no = int(run_id.split("_")[1])

        log_path = log_root / f"{run_id}.log"
        if not log_path.exists():
            raise FileNotFoundError(f"missing log: {log_path}")

        kv = parse_kv_log(log_path)
        start_epoch = int(kv["START_EPOCH"])
        end_epoch   = int(kv["END_EPOCH"])
        ready_epoch = int(kv["READY_EPOCH"]) if kv.get("READY_EPOCH", "").isdigit() else None

        t_total = end_epoch - start_epoch
        t_ready = (ready_epoch - start_epoch) if ready_epoch is not None else ""

        # csv 로드 (없으면 해당 지표만 스킵)
        cpu = load_df(run / "system_cpu.csv")
        ram = load_df(run / "system_ram.csv")

        du_path  = run / "disk_util_mmcblk0.csv"
        dio_path = run / "disk_io_mmcblk0.csv"
        du  = load_df(du_path) if du_path.exists() and du_path.stat().st_size > 0 else None
        dio = load_df(dio_path) if dio_path.exists() and dio_path.stat().st_size > 0 else None

        # CPU: user + system + iowait(있으면)
        cpu_total = safe_get(cpu, "user") + safe_get(cpu, "system") + safe_get(cpu, "iowait", 0.0)

        # RAM: used(있으면) 아니면 첫 데이터 컬럼
        ram_used = pick_ram_used(ram)

        # Disk util: utilization 컬럼 우선, 없으면 첫 데이터 컬럼
        if du is not None:
            disk_col = "utilization" if "utilization" in du.columns else [c for c in du.columns if c not in ("time","dt")][0]
            disk_util = du[disk_col].astype(float)
        else:
            disk_col = ""
            disk_util = None

        # Disk IO: reads/writes 우선
        if dio is not None:
            reads  = safe_get(dio, "reads").abs()
            writes = safe_get(dio, "writes").abs()
        else:
            reads = writes = None

        run_out = out_root / run_id
        ensure_dir(run_out)

        # (요구 형식) redacted.log 복사
        shutil.copy2(log_path, run_out / "redacted.log")

        # (요구 형식) fig1_timeseries.png: CPU/RAM/Disk util(+IO) 한 그림 + START/READY/END 표시
        nrows = 3 + (1 if (reads is not None and writes is not None) else 0)
        fig, ax = plt.subplots(nrows, 1, figsize=(12, 3*nrows), sharex=True)

        if nrows == 1:
            ax = [ax]

        ax[0].plot(cpu["dt"], cpu_total)
        ax[0].set_ylabel("CPU % (user+system+iowait)")

        ax[1].plot(ram["dt"], ram_used)
        ax[1].set_ylabel("RAM used")

        ax[2].set_ylabel("Disk util")
        if disk_util is not None:
            ax[2].plot(du["dt"], disk_util)

        idx = 3
        if reads is not None and writes is not None:
            ax[idx].plot(dio["dt"], reads, label="reads")
            ax[idx].plot(dio["dt"], writes, label="writes")
            ax[idx].set_ylabel("Disk IO (abs)")
            ax[idx].legend()

        # epoch 라인 표시(실제 dt축에 맞춰 찍기)
        def vline_epoch(a):
            a.axvline(pd.to_datetime(start_epoch, unit="s"), linestyle="--")
            if ready_epoch is not None:
                a.axvline(pd.to_datetime(ready_epoch, unit="s"), linestyle="--")
            a.axvline(pd.to_datetime(end_epoch, unit="s"), linestyle="--")

        for a in ax:
            vline_epoch(a)

        ax[-1].set_xlabel("time")
        fig.suptitle(f"{step} - {run_id}")
        fig.tight_layout()
        fig.savefig(run_out / "fig1_timeseries.png", dpi=200)
        plt.close(fig)

        # (요구 형식) stats.csv: mean/peak/auc + duration들
        row = {
            "step": step,
            "run": run_no,
            "START_EPOCH": start_epoch,
            "READY_EPOCH": ready_epoch if ready_epoch is not None else "",
            "END_EPOCH": end_epoch,
            "T_ready": t_ready,
            "T_total": t_total,

            "cpu_mean": float(cpu_total.mean()),
            "cpu_peak": float(cpu_total.max()),
            "cpu_auc":  auc(cpu_total, cpu["dt"]),

            "ram_mean": float(ram_used.mean()),
            "ram_peak": float(ram_used.max()),
            "ram_auc":  auc(ram_used, ram["dt"]),
        }

        if disk_util is not None:
            row.update({
                "disk_util_mean": float(disk_util.mean()),
                "disk_util_peak": float(disk_util.max()),
                "disk_util_auc":  auc(disk_util, du["dt"]),
                "disk_util_col": disk_col,
            })

        if reads is not None and writes is not None:
            row.update({
                "disk_read_mean": float(reads.mean()),
                "disk_read_peak": float(reads.max()),
                "disk_read_auc":  auc(reads, dio["dt"]),

                "disk_write_mean": float(writes.mean()),
                "disk_write_peak": float(writes.max()),
                "disk_write_auc":  auc(writes, dio["dt"]),
            })

        pd.DataFrame([row]).to_csv(run_out / "stats.csv", index=False)
        all_rows.append(row)

    # step summary
    df = pd.DataFrame(all_rows).sort_values("run")
    df.to_csv(out_root / "summary.csv", index=False)

    # (요구 형식) fig2_distribution.png: run 10회 이상이면 분포
    if len(df) >= 10:
        cols = [c for c in [
            "T_total",
            "cpu_mean", "cpu_peak", "cpu_auc",
            "ram_mean", "ram_peak", "ram_auc",
            "disk_util_mean", "disk_util_peak", "disk_util_auc",
            "disk_read_mean", "disk_write_mean",
        ] if c in df.columns]

        # 숫자 변환 가능한 것만
        cols2 = []
        for c in cols:
            s = pd.to_numeric(df[c], errors="coerce")
            if s.notna().sum() >= 3:
                df[c] = s
                cols2.append(c)

        if cols2:
            fig, ax = plt.subplots(len(cols2), 1, figsize=(12, 2.2*len(cols2)), sharex=False)
            if len(cols2) == 1:
                ax = [ax]
            for i, c in enumerate(cols2):
                ax[i].boxplot(df[c].dropna(), labels=[c])
                ax[i].set_ylabel("")
            fig.suptitle(f"{step} - Fig2 distribution (runs={len(df)})")
            fig.tight_layout()
            fig.savefig(out_root / "fig2_distribution.png", dpi=200)
            plt.close(fig)

    print(f"[OK] wrote: {out_root/'summary.csv'}")
    if (out_root / "fig2_distribution.png").exists():
        print(f"[OK] wrote: {out_root/'fig2_distribution.png'}")

if __name__ == "__main__":
    main()
