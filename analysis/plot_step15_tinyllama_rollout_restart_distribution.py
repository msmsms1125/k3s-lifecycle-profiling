#!/usr/bin/env python3
import argparse
from pathlib import Path
import math

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True)
    ap.add_argument("--runs", required=True, type=int)
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    step = args.step
    runs = args.runs

    step_dir = repo_root / "results" / step
    step_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for i in range(1, runs + 1):
        p = step_dir / f"run_{i}" / "stats.csv"
        if p.exists():
            df = pd.read_csv(p)
            if not df.empty:
                rows.append(df.iloc[0].to_dict())

    if not rows:
        raise SystemExit("No stats.csv found. Run per-run plot first.")

    summary = pd.DataFrame(rows).sort_values("run_id")
    summary.to_csv(step_dir / "summary.csv", index=False)

    metrics = [
        ("t_ready_sec", "T_ready (sec)"),
        ("cpu_peak", "CPU peak"),
        ("ram_peak", "RAM peak"),
        ("disk_peak", "Disk util peak"),
        ("net_rx_peak", "Net rx peak"),
        ("req_latency_p95_ms", "Req latency p95 (ms)"),
    ]

    vals = []
    labels = []
    for col, lab in metrics:
        if col in summary.columns:
            s = pd.to_numeric(summary[col], errors="coerce").dropna()
            if not s.empty:
                vals.append(s.to_numpy())
                labels.append(lab)

    if not vals:
        raise SystemExit("No metric columns available for Fig2.")

    fig_h = max(4, 0.6 * len(vals) + 2)
    fig = plt.figure(figsize=(12, fig_h))
    ax = fig.add_subplot(111)
    ax.boxplot(vals, vert=False, labels=labels, showmeans=True)
    ax.set_title(f"{step} - Fig2 distribution (n={len(summary)})")
    fig.tight_layout()
    fig.savefig(step_dir / "fig2_distribution.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
