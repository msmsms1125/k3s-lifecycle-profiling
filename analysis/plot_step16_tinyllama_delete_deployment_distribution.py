#!/usr/bin/env python3
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True)
    ap.add_argument("--runs", required=True, type=int)
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    step = args.step
    runs = args.runs

    step_result_dir = repo_root / "results" / step
    step_result_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for i in range(1, runs + 1):
        p = step_result_dir / f"run_{i}" / "stats.csv"
        if p.exists():
            df = pd.read_csv(p)
            rows.append(df.iloc[0].to_dict())
    if not rows:
        raise RuntimeError("no stats.csv found")

    summary = pd.DataFrame(rows).sort_values("run")
    summary.to_csv(step_result_dir / "summary.csv", index=False)

    metrics = [
        ("T_delete", "resource release duration (s)"),
        ("mem_release_latency_s", "memory release latency (s)"),
        ("idle_recovery_time_s", "idle recovery time (s)"),
    ]

    fig, axes = plt.subplots(1, len(metrics), figsize=(12, 4))
    if len(metrics) == 1:
        axes = [axes]

    for ax, (col, title) in zip(axes, metrics):
        vals = summary[col].to_numpy(dtype=float)
        ax.boxplot(vals, vert=True)
        ax.set_title(title)
        ax.set_xticks([1])
        ax.set_xticklabels([col])

    fig.tight_layout()
    fig.savefig(step_result_dir / "fig2_distribution.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
