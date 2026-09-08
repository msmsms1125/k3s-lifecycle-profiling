#!/usr/bin/env python3
import argparse
import csv
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import requests


@dataclass
class PromptItem:
    group: str
    text: str


def read_prompts(path: str) -> List[PromptItem]:
    items: List[PromptItem] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if "\t" in line:
                g, t = line.split("\t", 1)
                g = g.strip().lower()
                t = t.strip()
                if g in ("short", "medium", "long") and t:
                    items.append(PromptItem(g, t))
                    continue
            items.append(PromptItem("unknown", line))
    return items


def split_groups(items: List[PromptItem]) -> Tuple[List[str], List[str], List[str]]:
    short, med, long = [], [], []
    labeled = any(x.group in ("short", "medium", "long") for x in items)
    if labeled:
        for x in items:
            if x.group == "short":
                short.append(x.text)
            elif x.group == "medium":
                med.append(x.text)
            elif x.group == "long":
                long.append(x.text)
    else:
        texts = [x.text for x in items]
        if len(texts) < 60:
            raise ValueError(f"Need at least 60 prompts, got {len(texts)}")
        short, med, long = texts[:20], texts[20:40], texts[40:60]
    return short, med, long


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--endpoint-path", required=True)
    ap.add_argument("--prompts-file", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--rps", type=int, default=1)
    ap.add_argument("--load-duration-sec", type=int, default=60)
    ap.add_argument("--load-start-epoch", type=int, required=True)
    ap.add_argument("--n-predict", type=int, default=32)
    ap.add_argument("--temperature", type=float, default=0.1)
    ap.add_argument("--request-timeout-sec", type=float, default=120.0)
    args = ap.parse_args()

    if args.rps <= 0:
        raise ValueError("rps must be >= 1")
    if args.load_duration_sec <= 0:
        raise ValueError("load_duration_sec must be >= 1")
    if args.load_duration_sec % 3 != 0:
        raise ValueError("load_duration_sec must be divisible by 3")

    url = args.base_url.rstrip("/") + args.endpoint_path
    prompts = read_prompts(args.prompts_file)
    short_list, med_list, long_list = split_groups(prompts)

    seg = args.load_duration_sec // 3
    if len(short_list) < seg or len(med_list) < seg or len(long_list) < seg:
        raise ValueError(f"Need >= {seg} prompts per group")

    plan: List[Tuple[int, str, str]] = []
    for i in range(args.load_duration_sec):
        if i < seg:
            plan.append((i, "short", short_list[i]))
        elif i < 2 * seg:
            plan.append((i, "medium", med_list[i - seg]))
        else:
            plan.append((i, "long", long_list[i - 2 * seg]))

    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "run_id",
                "req_idx",
                "group",
                "prompt_chars",
                "scheduled_ts",
                "sent_ts",
                "first_token_ts",
                "done_ts",
                "queue_delay_sec",
                "ttft_sec",
                "total_sec",
                "http_status",
                "error",
            ]
        )

        for req_idx, group, prompt in plan:
            scheduled_ts = float(args.load_start_epoch + req_idx / args.rps)
            now = time.time()
            if now < scheduled_ts:
                time.sleep(scheduled_ts - now)

            sent_ts = time.time()
            first_token_ts: Optional[float] = None
            done_ts: Optional[float] = None
            status: Optional[int] = None
            err: Optional[str] = None

            try:
                payload = {
                    "prompt": prompt,
                    "max_tokens": args.n_predict,
                    "temperature": args.temperature,
                    "stream": True,
                }
                resp = requests.post(
                    url, json=payload, stream=True, timeout=args.request_timeout_sec
                )
                status = resp.status_code

                for chunk in resp.iter_content(chunk_size=1):
                    if chunk:
                        first_token_ts = time.time()
                        break

                for _ in resp.iter_content(chunk_size=8192):
                    pass
                done_ts = time.time()
            except Exception as e:
                err = f"{type(e).__name__}:{e}"
                done_ts = time.time()

            queue_delay = sent_ts - scheduled_ts
            ttft = (first_token_ts - sent_ts) if (first_token_ts is not None) else ""
            total = (done_ts - sent_ts) if (done_ts is not None) else ""

            w.writerow(
                [
                    args.run_id,
                    req_idx,
                    group,
                    len(prompt),
                    f"{scheduled_ts:.6f}",
                    f"{sent_ts:.6f}",
                    (f"{first_token_ts:.6f}" if first_token_ts is not None else ""),
                    (f"{done_ts:.6f}" if done_ts is not None else ""),
                    f"{queue_delay:.6f}",
                    (f"{ttft:.6f}" if ttft != "" else ""),
                    (f"{total:.6f}" if total != "" else ""),
                    (status if status is not None else ""),
                    (err if err is not None else ""),
                ]
            )


if __name__ == "__main__":
    main()
