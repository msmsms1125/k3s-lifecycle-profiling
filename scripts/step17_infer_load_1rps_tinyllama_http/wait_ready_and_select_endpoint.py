#!/usr/bin/env python3
import argparse, json, time
from typing import Dict, List, Tuple
import requests

def try_completion(url: str, n_predict: int, temperature: float, timeout: float) -> Tuple[bool, int]:
    payload = {"prompt": "Hello", "n_predict": n_predict, "max_tokens": n_predict, "temperature": temperature, "stream": False}
    r = requests.post(url, json=payload, timeout=timeout)
    return (200 <= r.status_code < 300), r.status_code

def try_chat(url: str, n_predict: int, temperature: float, timeout: float) -> Tuple[bool, int]:
    payload = {"messages": [{"role": "user", "content": "Hello"}], "n_predict": n_predict, "max_tokens": n_predict, "temperature": temperature, "stream": False}
    r = requests.post(url, json=payload, timeout=timeout)
    return (200 <= r.status_code < 300), r.status_code

def parse_candidates(s: str) -> List[str]:
    return [x.strip() for x in s.split(",") if x.strip()]

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--n-predict", type=int, default=32)
    ap.add_argument("--temperature", type=float, default=0.1)
    ap.add_argument("--timeout-sec", type=int, default=300)
    ap.add_argument("--request-timeout-sec", type=float, default=10.0)
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    candidates = parse_candidates(args.candidates)

    deadline = time.time() + args.timeout_sec
    last_err: Dict[str, str] = {}

    while time.time() < deadline:
        for path in candidates:
            url = base + path
            try:
                ok, code = try_completion(url, args.n_predict, args.temperature, args.request_timeout_sec)
                if ok:
                    print(json.dumps({"ready_epoch": int(time.time()), "endpoint_path": path, "mode": "completions", "http_status": code}))
                    return
            except Exception as e:
                last_err[url] = f"completion:{type(e).__name__}:{e}"

            try:
                ok, code = try_chat(url, args.n_predict, args.temperature, args.request_timeout_sec)
                if ok:
                    print(json.dumps({"ready_epoch": int(time.time()), "endpoint_path": path, "mode": "chat", "http_status": code}))
                    return
            except Exception as e:
                last_err[url] = f"chat:{type(e).__name__}:{e}"

        time.sleep(1.0)

    print(json.dumps({"ready_epoch": None, "endpoint_path": None, "mode": None, "error": "READY timeout", "last_err": last_err}))
    raise SystemExit(2)

if __name__ == "__main__":
    main()
