import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

STEP = "step12_apply_tinyllama_http"
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESULT_BASE = os.path.join(BASE_DIR, "results", STEP)


def load_summary():
    path = os.path.join(RESULT_BASE, "summary.csv")
    if not os.path.exists(path):
        per_run = []
        for i in range(1, 11):
            p = os.path.join(RESULT_BASE, f"run_{i}", "stats.csv")
            if os.path.exists(p):
                df = pd.read_csv(p)
                per_run.append(df)
        if not per_run:
            return None
        return pd.concat(per_run, ignore_index=True)
    return pd.read_csv(path)


def violin_or_box(ax, data, label, color):
    clean = [x for x in data if not np.isnan(x)]
    if len(clean) < 2:
        ax.bar([0], [clean[0]] if clean else [0], color=color, alpha=0.7, width=0.4)
    else:
        parts = ax.violinplot([clean], positions=[0], showmedians=True, showextrema=True)
        for pc in parts["bodies"]:
            pc.set_facecolor(color)
            pc.set_alpha(0.6)
        parts["cmedians"].set_color("black")
        parts["cmedians"].set_linewidth(2)
        ax.scatter([0] * len(clean), clean, color="black", s=20, zorder=3, alpha=0.7)
    mean_val = np.nanmean(data)
    std_val = np.nanstd(data)
    ax.set_title(f"{label}\n$\\mu$={mean_val:.1f}  $\\sigma$={std_val:.1f}", fontsize=9)
    ax.set_xticks([])
    ax.grid(True, axis="y", alpha=0.3)


def main():
    df = load_summary()
    if df is None or df.empty:
        print("No summary data found. Run plot_step12_tinyllama.py first.")
        sys.exit(1)

    metrics = [
        ("T_ready", "T_ready (s)", "tab:blue"),
        ("T_total", "T_total (s)", "tab:cyan"),
        ("cpu_mean", "CPU Mean (%)", "tab:orange"),
        ("cpu_peak", "CPU Peak (%)", "tab:red"),
        ("ram_mean", "RAM Mean (MB)", "tab:green"),
        ("ram_peak", "RAM Peak (MB)", "tab:olive"),
        ("disk_mean", "Disk Mean (%)", "tab:purple"),
        ("disk_peak", "Disk Peak (%)", "tab:pink"),
        ("net_rx_peak", "Net Rx Peak (KB/s)", "tab:brown"),
        ("net_tx_peak", "Net Tx Peak (KB/s)", "tab:gray"),
    ]

    available = [(col, label, color) for col, label, color in metrics if col in df.columns]
    n = len(available)
    cols = 5
    rows = (n + cols - 1) // cols

    fig = plt.figure(figsize=(cols * 3.2, rows * 3.5))
    gs = gridspec.GridSpec(rows, cols, figure=fig, hspace=0.7, wspace=0.4)

    for idx, (col, label, color) in enumerate(available):
        ax = fig.add_subplot(gs[idx // cols, idx % cols])
        data = df[col].values.astype(float)
        violin_or_box(ax, data, label, color)

    n_runs = len(df)
    fig.suptitle(
        f"[{STEP}] Distribution over {n_runs} runs\n"
        f"Fig2 — Resource Peaks & Timing",
        fontsize=12, fontweight="bold", y=1.01
    )

    out_path = os.path.join(RESULT_BASE, "fig2_distribution.png")
    os.makedirs(RESULT_BASE, exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Fig2 saved: {out_path}")

    print("\n=== Summary Statistics ===")
    stat_cols = [col for col, _, _ in available if col in df.columns]
    summary = df[stat_cols].agg(["mean", "std", "min", "max"]).round(2)
    print(summary.to_string())


if __name__ == "__main__":
    main()
