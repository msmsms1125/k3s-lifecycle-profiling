#!/usr/bin/env python3
import argparse, os
import pandas as pd
import matplotlib.pyplot as plt

def repo_root_from_here() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True)
    ap.add_argument("--runs", type=int, default=10)
    args = ap.parse_args()

    root = repo_root_from_here()
    step = args.step
    runs = args.runs

    rows = []
    for r in range(1, runs + 1):
        p = os.path.join(root, "results", step, f"run_{r}", "stats.csv")
        if os.path.exists(p):
            df = pd.read_csv(p)
            rows.append(df.iloc[0].to_dict())

    if not rows:
        raise SystemExit("No stats.csv found")

    out_step = os.path.join(root, "results", step)
    os.makedirs(out_step, exist_ok=True)

    summary = pd.DataFrame(rows).sort_values("run")
    summary.to_csv(os.path.join(out_step, "summary.csv"), index=False)

    metrics = ["ttft_mean", "total_mean", "cpu_peak", "ram_peak", "disk_peak", "net_rx_peak"]
    fig, axes = plt.subplots(2, 3, figsize=(14, 7))
    axes = axes.flatten()

    for ax, m in zip(axes, metrics):
        ax.boxplot(summary[m].dropna().values)
        ax.set_title(m)

    fig.tight_layout()
    fig.savefig(os.path.join(out_step, "fig2_distribution.png"), dpi=150)
    plt.close(fig)

if __name__ == "__main__":
    main()
