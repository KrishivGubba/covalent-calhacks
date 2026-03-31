#!/usr/bin/env python3
"""
Measure API readiness and request latency for parity/performance tracking.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests


def wait_for_healthy(url: str, timeout_s: float) -> Optional[float]:
    start = time.perf_counter()
    deadline = start + timeout_s
    while time.perf_counter() < deadline:
        try:
            resp = requests.get(f"{url.rstrip('/')}/health", timeout=1.5)
            if resp.status_code == 200:
                return time.perf_counter() - start
        except Exception:
            pass
        time.sleep(0.2)
    return None


def measure_endpoint(url: str, method: str, path: str, body: Optional[Dict[str, Any]], samples: int) -> Dict[str, Any]:
    latencies = []
    status_codes = []
    full_url = f"{url.rstrip('/')}{path}"

    for _ in range(samples):
        t0 = time.perf_counter()
        resp = requests.request(method=method, url=full_url, json=body, timeout=10)
        dt_ms = (time.perf_counter() - t0) * 1000
        latencies.append(dt_ms)
        status_codes.append(resp.status_code)

    return {
        "path": path,
        "method": method,
        "samples": samples,
        "status_codes": status_codes,
        "latency_ms": {
            "min": min(latencies),
            "p50": statistics.median(latencies),
            "p95": sorted(latencies)[max(0, int(0.95 * len(latencies)) - 1)],
            "max": max(latencies),
            "avg": statistics.mean(latencies),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure API startup and latency")
    parser.add_argument("--url", required=True, help="Base URL (example: http://127.0.0.1:15002)")
    parser.add_argument("--start-cmd", default=None, help="Optional command to spawn server before measuring")
    parser.add_argument("--startup-timeout", type=float, default=30.0)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--out", default="tests/parity/perf_report.json")
    args = parser.parse_args()

    proc = None
    try:
        startup_time_s = None
        if args.start_cmd:
            proc = subprocess.Popen(args.start_cmd, shell=True)
            startup_time_s = wait_for_healthy(args.url, args.startup_timeout)
            if startup_time_s is None:
                raise RuntimeError("Server did not become healthy before timeout")

        report = {
            "url": args.url,
            "startup_time_s": startup_time_s,
            "generated_at_epoch_s": time.time(),
            "benchmarks": [
                measure_endpoint(args.url, "GET", "/health", None, args.samples),
                measure_endpoint(
                    args.url,
                    "POST",
                    "/tab_predict",
                    {
                        "app_name": "Terminal",
                        "text_buffer": "import",
                        "context_type": "full_query",
                        "activity_id": "perf_probe",
                    },
                    args.samples,
                ),
            ],
        }

        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print(json.dumps(report, indent=2))
        return 0
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
