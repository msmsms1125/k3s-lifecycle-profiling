from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "step17_infer_load_1rps_tinyllama_http" / "load_1rps.py"


def load_module():
    spec = importlib.util.spec_from_file_location("load_1rps", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


load_1rps = load_module()


class SlowSSEHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        time.sleep(1.0)
        body = b'data: {"choices":[{"text":"token"}]}\n\ndata: [DONE]\n\n'
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


class LoadGeneratorUnitTests(unittest.TestCase):
    def test_first_generated_token_rejects_metadata_and_done(self):
        self.assertFalse(load_1rps.first_generated_token("data: [DONE]"))
        self.assertFalse(
            load_1rps.first_generated_token('data: {"choices":[{"text":""}]}')
        )
        self.assertTrue(
            load_1rps.first_generated_token('data: {"choices":[{"text":"x"}]}')
        )
        self.assertTrue(
            load_1rps.first_generated_token(
                'data: {"choices":[{"delta":{"content":"x"}}]}'
            )
        )

    def test_plan_uses_wall_clock_intervals_and_three_segments(self):
        groups = (["s"], ["m"], ["l"])
        plan = load_1rps.build_plan(
            load_start_epoch=100.0,
            load_duration_sec=6,
            rps=2.0,
            groups=groups,
        )
        self.assertEqual(12, len(plan))
        self.assertEqual(["short"] * 4 + ["medium"] * 4 + ["long"] * 4, [row[1] for row in plan])
        self.assertEqual([100.0 + index * 0.5 for index in range(12)], [row[3] for row in plan])


class LoadGeneratorIntegrationTest(unittest.TestCase):
    def test_slow_responses_do_not_reduce_dispatch_rate(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), SlowSSEHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp = Path(temp_dir)
                prompts = temp / "prompts.txt"
                prompts.write_text(
                    "short\tshort prompt\nmedium\tmedium prompt\nlong\tlong prompt\n",
                    encoding="utf-8",
                )
                output = temp / "requests.csv"
                # Leave enough startup margin for slower CI runners. The load
                # generator intentionally refuses to catch up a missed schedule.
                load_start = time.time() + 1.5
                started = time.monotonic()
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--base-url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--endpoint-path",
                        "/v1/completions",
                        "--prompts-file",
                        str(prompts),
                        "--out-csv",
                        str(output),
                        "--run-id",
                        "ci",
                        "--rps",
                        "2",
                        "--load-duration-sec",
                        "3",
                        "--load-start-epoch",
                        str(load_start),
                        "--request-timeout-sec",
                        "5",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                elapsed = time.monotonic() - started
                self.assertEqual(
                    0,
                    completed.returncode,
                    f"load generator stderr:\n{completed.stderr}",
                )
                summary = json.loads(completed.stdout)
                with output.open(newline="", encoding="utf-8") as handle:
                    rows = list(csv.DictReader(handle))

            sent = [float(row["sent_ts"]) for row in rows]
            intervals = [right - left for left, right in zip(sent, sent[1:])]
            self.assertEqual(6, len(rows))
            self.assertEqual(6, summary["successful_requests"])
            self.assertGreater(summary["achieved_dispatch_rps"], 1.6)
            self.assertLess(max(intervals), 0.8)
            self.assertLess(elapsed, 6.5)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
