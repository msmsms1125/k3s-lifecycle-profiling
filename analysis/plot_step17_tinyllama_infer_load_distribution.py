#!/usr/bin/env python3
import argparse
import os

import matplotlib.pyplot as plt
import pandas as pd


def repo_root_from_here() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", required=True)
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()

    root = repo_root_from_here()
    rows = []
    for run in range(1, args.runs + 1):
        path = os.path.join(root, "results", args.step, f"run_{run}", "stats.csv")
        if os.path.exists(path):
            rows.append(pd.read_csv(path).iloc[0].to_dict())

    if not rows:
        raise SystemExit("No stats.csv found")

    summary = pd.DataFrame(rows).sort_values("run")
    if "data_quality_status" not in summary.columns or not summary[
        "data_quality_status"
    ].eq("validated").all():
        raise SystemExit(
            "Refusing to mix legacy/unvalidated step17 results with corrected results"
        )

    metrics = [
        "ttft_p50",
        "total_p95",
        "success_rate",
        "dispatch_delay_p95",
        "cpu_peak",
        "ram_peak",
    ]
    missing = [metric for metric in metrics if metric not in summary.columns]
    if missing:
        raise SystemExit(f"Missing validated metrics: {missing}")

    out_step = os.path.join(root, "results", args.step)
    os.makedirs(out_step, exist_ok=True)
    summary.to_csv(os.path.join(out_step, "summary.csv"), index=False)

    fig, axes = plt.subplots(2, 3, figsize=(14, 7))
    for axis, metric in zip(axes.flatten(), metrics):
        axis.boxplot(summary[metric].dropna().values)
        axis.set_title(metric)
    fig.tight_layout()
    fig.savefig(os.path.join(out_step, "fig2_distribution.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
