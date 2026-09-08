#!/usr/bin/env python3
"""Open-loop HTTP load generator for llama.cpp's completion endpoint.

Requests are dispatched on the configured wall-clock schedule. A slow response does
not delay dispatch of the next request; server-side queueing is therefore visible in
TTFT/latency instead of being accidentally introduced by the client loop.
"""

import argparse
import csv
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import List, Optional, Tuple

import requests


@dataclass(frozen=True)
class PromptItem:
    group: str
    text: str


@dataclass
class RequestResult:
    run_id: str
    req_idx: int
    group: str
    prompt_chars: int
    scheduled_ts: float
    sent_ts: float
    first_token_ts: Optional[float]
    done_ts: float
    dispatch_delay_sec: float
    ttft_sec: Optional[float]
    total_sec: float
    http_status: Optional[int]
    error: Optional[str]


def read_prompts(path: str) -> List[PromptItem]:
    items: List[PromptItem] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if "\t" in line:
                group, prompt = line.split("\t", 1)
                group = group.strip().lower()
                prompt = prompt.strip()
                if group in ("short", "medium", "long") and prompt:
                    items.append(PromptItem(group, prompt))
                    continue
            items.append(PromptItem("unknown", line))
    return items


def split_groups(items: List[PromptItem]) -> Tuple[List[str], List[str], List[str]]:
    labeled = any(item.group != "unknown" for item in items)
    if labeled:
        groups = {
            name: [item.text for item in items if item.group == name]
            for name in ("short", "medium", "long")
        }
        missing = [name for name, values in groups.items() if not values]
        if missing:
            raise ValueError(f"Prompt groups are empty: {', '.join(missing)}")
        return groups["short"], groups["medium"], groups["long"]

    texts = [item.text for item in items]
    if len(texts) < 60:
        raise ValueError(f"Need 60 unlabeled prompts, got {len(texts)}")
    return texts[:20], texts[20:40], texts[40:60]


def first_generated_token(line: str) -> bool:
    """Return True only for an SSE event that contains generated text."""
    line = line.strip()
    if not line or not line.startswith("data:"):
        return False
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return False
    try:
        body = json.loads(payload)
    except json.JSONDecodeError:
        return False
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return False
    choice = choices[0]
    if not isinstance(choice, dict):
        return False
    text = choice.get("text")
    if isinstance(text, str) and text:
        return True
    delta = choice.get("delta")
    return isinstance(delta, dict) and bool(delta.get("content"))


def execute_request(
    *,
    run_id: str,
    req_idx: int,
    group: str,
    prompt: str,
    scheduled_ts: float,
    url: str,
    n_predict: int,
    temperature: float,
    timeout_sec: float,
) -> RequestResult:
    now = time.time()
    if now < scheduled_ts:
        time.sleep(scheduled_ts - now)

    sent_ts = time.time()
    first_token_ts: Optional[float] = None
    status: Optional[int] = None
    error: Optional[str] = None

    try:
        with requests.post(
            url,
            json={
                "prompt": prompt,
                "max_tokens": n_predict,
                "temperature": temperature,
                "stream": True,
            },
            stream=True,
            timeout=timeout_sec,
        ) as response:
            status = response.status_code
            if 200 <= status < 300:
                for raw_line in response.iter_lines(chunk_size=1, decode_unicode=True):
                    line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", "replace")
                    if first_token_ts is None and first_generated_token(line):
                        first_token_ts = time.time()
                if first_token_ts is None:
                    error = "NoGeneratedToken"
            else:
                error = f"HTTPError:{status}"
    except Exception as exc:  # The error is recorded per request; the run still completes.
        error = f"{type(exc).__name__}:{exc}".replace("\n", " ")

    done_ts = time.time()
    return RequestResult(
        run_id=run_id,
        req_idx=req_idx,
        group=group,
        prompt_chars=len(prompt),
        scheduled_ts=scheduled_ts,
        sent_ts=sent_ts,
        first_token_ts=first_token_ts,
        done_ts=done_ts,
        dispatch_delay_sec=sent_ts - scheduled_ts,
        ttft_sec=(first_token_ts - sent_ts) if first_token_ts is not None else None,
        total_sec=done_ts - sent_ts,
        http_status=status,
        error=error,
    )


def build_plan(
    *,
    load_start_epoch: float,
    load_duration_sec: int,
    rps: float,
    groups: Tuple[List[str], List[str], List[str]],
) -> List[Tuple[int, str, str, float]]:
    total_requests = int(round(load_duration_sec * rps))
    if total_requests < 3:
        raise ValueError("The load plan must contain at least three requests")

    names = ("short", "medium", "long")
    counters = [0, 0, 0]
    plan: List[Tuple[int, str, str, float]] = []
    for req_idx in range(total_requests):
        offset_sec = req_idx / rps
        segment = min(2, int(offset_sec * 3 / load_duration_sec))
        prompts = groups[segment]
        prompt = prompts[counters[segment] % len(prompts)]
        counters[segment] += 1
        plan.append((req_idx, names[segment], prompt, load_start_epoch + offset_sec))
    return plan


def optional_number(value: Optional[float]) -> str:
    return "" if value is None else f"{value:.6f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--endpoint-path", required=True)
    parser.add_argument("--prompts-file", required=True)
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--rps", type=float, default=1.0)
    parser.add_argument("--load-duration-sec", type=int, default=60)
    parser.add_argument("--load-start-epoch", type=float, required=True)
    parser.add_argument("--n-predict", type=int, default=32)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--request-timeout-sec", type=float, default=120.0)
    parser.add_argument("--max-workers", type=int, default=0)
    args = parser.parse_args()

    if args.rps <= 0 or args.load_duration_sec <= 0:
        raise ValueError("rps and load-duration-sec must be positive")

    url = args.base_url.rstrip("/") + args.endpoint_path
    groups = split_groups(read_prompts(args.prompts_file))
    plan = build_plan(
        load_start_epoch=args.load_start_epoch,
        load_duration_sec=args.load_duration_sec,
        rps=args.rps,
        groups=groups,
    )
    if args.load_start_epoch < time.time() + 0.5:
        raise ValueError(
            "load-start-epoch must be at least 0.5 seconds in the future; "
            "refusing to catch up missed dispatches as a burst"
        )

    estimated_concurrency = math.ceil(args.rps * args.request_timeout_sec) + 2
    max_workers = args.max_workers or min(128, len(plan), max(8, estimated_concurrency))
    if max_workers <= 0:
        raise ValueError("max-workers must be positive")

    futures = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for req_idx, group, prompt, scheduled_ts in plan:
            now = time.time()
            if now < scheduled_ts:
                time.sleep(scheduled_ts - now)
            futures.append(
                pool.submit(
                    execute_request,
                    run_id=args.run_id,
                    req_idx=req_idx,
                    group=group,
                    prompt=prompt,
                    scheduled_ts=scheduled_ts,
                    url=url,
                    n_predict=args.n_predict,
                    temperature=args.temperature,
                    timeout_sec=args.request_timeout_sec,
                )
            )
        results = [future.result() for future in as_completed(futures)]

    results.sort(key=lambda item: item.req_idx)
    fieldnames = list(asdict(results[0]).keys())
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = asdict(result)
            for key in ("scheduled_ts", "sent_ts", "first_token_ts", "done_ts", "dispatch_delay_sec", "ttft_sec", "total_sec"):
                row[key] = optional_number(row[key])
            row["http_status"] = "" if row["http_status"] is None else row["http_status"]
            row["error"] = row["error"] or ""
            writer.writerow(row)

    sent_times = [item.sent_ts for item in results]
    achieved_dispatch_rps = (
        (len(sent_times) - 1) / (max(sent_times) - min(sent_times))
        if len(sent_times) > 1 and max(sent_times) > min(sent_times)
        else math.nan
    )
    successes = sum(item.http_status is not None and 200 <= item.http_status < 300 for item in results)
    print(
        json.dumps(
            {
                "planned_requests": len(results),
                "planned_rps": args.rps,
                "achieved_dispatch_rps": achieved_dispatch_rps,
                "successful_requests": successes,
                "max_workers": max_workers,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
