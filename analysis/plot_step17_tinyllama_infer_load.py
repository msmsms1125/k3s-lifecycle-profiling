#!/usr/bin/env python3
import argparse
import os
from typing import Iterable, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def repo_root_from_here() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def read_kv_log(path: str) -> dict:
    values = {}
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if line and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def read_netdata_csv(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path, comment="#")
    if frame.empty:
        raise ValueError(f"Empty Netdata CSV: {path}")
    return frame


def time_col(frame: pd.DataFrame) -> str:
    for column in frame.columns:
        if column.strip().lower() in ("time", "timestamp"):
            return column
    return frame.columns[0]


def find_col(frame: pd.DataFrame, candidates: Sequence[str], metric: str) -> str:
    value_columns = [column for column in frame.columns if column != time_col(frame)]
    normalized = {column.strip().lower(): column for column in value_columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    partial = [
        column
        for column in value_columns
        if any(candidate in column.strip().lower() for candidate in candidates)
    ]
    if len(partial) == 1:
        return partial[0]
    raise ValueError(
        f"Cannot select an unambiguous {metric} column; columns={value_columns}"
    )


def parse_time_series(series: pd.Series) -> np.ndarray:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().all():
        return numeric.to_numpy(dtype=float)
    parsed = pd.to_datetime(series, errors="raise")
    if parsed.dt.tz is None:
        parsed = parsed.dt.tz_localize("Asia/Seoul")
    return (parsed.astype("int64") / 1e9).to_numpy(dtype=float)


def sorted_series(
    frame: pd.DataFrame, values: Iterable[float], name: str
) -> tuple[np.ndarray, np.ndarray]:
    series = pd.DataFrame(
        {
            "time": parse_time_series(frame[time_col(frame)]),
            "value": np.asarray(values, dtype=float),
        }
    )
    series = (
        series.replace([np.inf, -np.inf], np.nan)
        .dropna()
        .sort_values("time")
        .drop_duplicates("time", keep="last")
    )
    if len(series) < 2:
        raise ValueError(f"{name} needs at least two valid timestamps")
    timestamps = series["time"].to_numpy(dtype=float)
    if np.any(np.diff(timestamps) <= 0):
        raise ValueError(f"{name} timestamps are not strictly increasing")
    return timestamps, series["value"].to_numpy(dtype=float)


def validate_range(
    name: str, values: np.ndarray, *, minimum: float, maximum: float | None = None
) -> None:
    observed_min = float(np.min(values))
    observed_max = float(np.max(values))
    if observed_min < minimum or (maximum is not None and observed_max > maximum):
        expected = f"[{minimum}, {maximum}]" if maximum is not None else f">= {minimum}"
        raise ValueError(
            f"{name} outside expected range {expected}: min={observed_min}, max={observed_max}"
        )


def auc(timestamps: np.ndarray, values: np.ndarray) -> float:
    widths = np.diff(timestamps)
    result = float(np.sum(widths * (values[:-1] + values[1:]) / 2.0))
    if result < 0:
        raise ValueError(f"AUC must be non-negative after time sorting, got {result}")
    return result


def percentile(series: pd.Series, q: float) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.quantile(q)) if not values.empty else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", required=True)
    parser.add_argument("--run", type=int, required=True)
    args = parser.parse_args()

    root = repo_root_from_here()
    step = args.step
    run = args.run
    log_file = os.path.join(root, "logs", "redacted", step, f"run_{run}.log")
    request_file = os.path.join(root, "logs", "redacted", step, f"run_{run}_requests.csv")
    net_dir = os.path.join(root, "data", "netdata", step, f"run_{run}")
    out_dir = os.path.join(root, "results", step, f"run_{run}")
    os.makedirs(out_dir, exist_ok=True)

    meta = read_kv_log(log_file)
    required_epochs = ("START_EPOCH", "READY_EPOCH", "LOAD_START_EPOCH", "LOAD_END_EPOCH", "END_EPOCH")
    missing_epochs = [key for key in required_epochs if key not in meta]
    if missing_epochs:
        raise ValueError(f"Missing event timestamps: {missing_epochs}")
    epochs = {key: int(meta[key]) for key in required_epochs}
    requests_done = int(meta.get("REQUESTS_DONE_EPOCH", epochs["LOAD_END_EPOCH"]))

    requests_frame = pd.read_csv(request_file)
    required_request_columns = {
        "http_status",
        "dispatch_delay_sec",
        "ttft_sec",
        "total_sec",
        "sent_ts",
        "error",
    }
    missing_columns = required_request_columns.difference(requests_frame.columns)
    if missing_columns:
        raise ValueError(
            "Legacy request CSV cannot be validated as open-loop load: "
            f"missing {sorted(missing_columns)}"
        )
    if requests_frame.empty:
        raise ValueError("Request CSV is empty")

    status = pd.to_numeric(requests_frame["http_status"], errors="coerce")
    errors = requests_frame["error"].fillna("").astype(str).str.strip()
    success_mask = status.between(200, 299) & errors.eq("")
    success_rate = float(success_mask.mean())
    sent = pd.to_numeric(requests_frame["sent_ts"], errors="coerce").dropna()
    achieved_rps = (
        float((len(sent) - 1) / (sent.max() - sent.min()))
        if len(sent) > 1 and sent.max() > sent.min()
        else float("nan")
    )

    cpu = read_netdata_csv(os.path.join(net_dir, "system_cpu.csv"))
    ram = read_netdata_csv(os.path.join(net_dir, "system_ram.csv"))
    disk = read_netdata_csv(os.path.join(net_dir, "disk_util_mmcblk0.csv"))
    network = read_netdata_csv(os.path.join(net_dir, "net_eth0.csv"))

    idle_column = find_col(cpu, ("idle",), "CPU idle")
    cpu_t, cpu_used = sorted_series(cpu, 100.0 - pd.to_numeric(cpu[idle_column]), "CPU")
    ram_column = find_col(ram, ("used",), "RAM used")
    ram_t, ram_used = sorted_series(ram, pd.to_numeric(ram[ram_column]), "RAM")
    disk_column = find_col(disk, ("utilization", "util", "busy"), "disk utilization")
    disk_t, disk_util = sorted_series(disk, pd.to_numeric(disk[disk_column]), "disk")
    rx_column = find_col(network, ("received", "recv", "rx"), "network receive")
    tx_column = find_col(network, ("sent", "send", "tx"), "network transmit")
    net_t, net_rx = sorted_series(network, np.abs(pd.to_numeric(network[rx_column])), "network receive")
    net_t_tx, net_tx = sorted_series(network, np.abs(pd.to_numeric(network[tx_column])), "network transmit")
    if not np.array_equal(net_t, net_t_tx):
        raise ValueError("Network receive/transmit timestamps do not align")

    validate_range("CPU used percent", cpu_used, minimum=0.0, maximum=100.0)
    validate_range("RAM used", ram_used, minimum=0.0)
    validate_range("Disk utilization percent", disk_util, minimum=0.0, maximum=100.0)
    validate_range("Network receive", net_rx, minimum=0.0)
    validate_range("Network transmit", net_tx, minimum=0.0)

    success_requests = requests_frame.loc[success_mask]
    stats = pd.DataFrame(
        [
            {
                "run": run,
                **epochs,
                "REQUESTS_DONE_EPOCH": requests_done,
                "data_quality_status": "validated",
                "planned_rps": float(meta["RPS"]),
                "request_count": int(len(requests_frame)),
                "success_rate": success_rate,
                "achieved_dispatch_rps": achieved_rps,
                "dispatch_delay_mean": float(
                    pd.to_numeric(requests_frame["dispatch_delay_sec"], errors="coerce").mean()
                ),
                "dispatch_delay_p95": percentile(requests_frame["dispatch_delay_sec"], 0.95),
                "ttft_mean": float(pd.to_numeric(success_requests["ttft_sec"], errors="coerce").mean()),
                "ttft_p50": percentile(success_requests["ttft_sec"], 0.5),
                "ttft_p95": percentile(success_requests["ttft_sec"], 0.95),
                "total_mean": float(pd.to_numeric(success_requests["total_sec"], errors="coerce").mean()),
                "total_p50": percentile(success_requests["total_sec"], 0.5),
                "total_p95": percentile(success_requests["total_sec"], 0.95),
                "cpu_mean": float(np.mean(cpu_used)),
                "cpu_peak": float(np.max(cpu_used)),
                "cpu_auc_pct_sec": auc(cpu_t, cpu_used),
                "ram_mean": float(np.mean(ram_used)),
                "ram_peak": float(np.max(ram_used)),
                "ram_auc_unit_sec": auc(ram_t, ram_used),
                "disk_mean": float(np.mean(disk_util)),
                "disk_peak": float(np.max(disk_util)),
                "disk_auc_pct_sec": auc(disk_t, disk_util),
                "net_rx_peak": float(np.max(net_rx)),
                "net_tx_peak": float(np.max(net_tx)),
                "net_rx_auc_unit_sec": auc(net_t, net_rx),
                "net_tx_auc_unit_sec": auc(net_t, net_tx),
            }
        ]
    )
    stats.to_csv(os.path.join(out_dir, "stats.csv"), index=False)

    start_epoch = epochs["START_EPOCH"]
    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
    axes[0].plot(cpu_t - start_epoch, cpu_used)
    axes[0].set_title("CPU used (%)")
    axes[1].plot(ram_t - start_epoch, ram_used)
    axes[1].set_title(f"RAM used (Netdata column: {ram_column})")
    axes[2].plot(disk_t - start_epoch, disk_util)
    axes[2].set_title("Disk utilization (%)")
    axes[3].plot(net_t - start_epoch, net_rx, label="received magnitude")
    axes[3].plot(net_t - start_epoch, net_tx, label="sent magnitude")
    axes[3].legend()
    axes[3].set_title("Network throughput (Netdata chart units)")

    markers = [
        (epochs["READY_EPOCH"], "READY"),
        (epochs["LOAD_START_EPOCH"], "LOAD_START"),
        (epochs["LOAD_END_EPOCH"], "SCHEDULE_END"),
        (requests_done, "REQUESTS_DONE"),
        (epochs["END_EPOCH"], "END"),
    ]
    for axis in axes:
        for timestamp, label in markers:
            x = timestamp - start_epoch
            axis.axvline(x, linewidth=0.8, linestyle="--")
            axis.text(x, axis.get_ylim()[1], label, va="top", fontsize=7)

    axes[-1].set_xlabel("seconds since START")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "fig1_timeseries.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
