#!/usr/bin/env python3
"""
Run repeated and concurrent determinism checks against a single API base URL.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
from pathlib import Path
from typing import Any, Dict, List

import requests


def extract_path(data: Any, path: str) -> Any:
    current = data
    for token in path.split("."):
        if "[" in token and token.endswith("]"):
            key, idx = token[:-1].split("[", 1)
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
            if not isinstance(current, list):
                return None
            if idx == "*":
                return current
            i = int(idx)
            if i < 0 or i >= len(current):
                return None
            current = current[i]
        else:
            if not isinstance(current, dict) or token not in current:
                return None
            current = current[token]
    return current


def make_request(base_url: str, case: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
    method = case.get("method", "GET").upper()
    url = f"{base_url.rstrip('/')}{case['path']}"
    resp = requests.request(method=method, url=url, params=case.get("query"), json=case.get("body"), timeout=timeout_s)
    try:
        payload = resp.json()
    except Exception:
        payload = None

    signature = {
        "status_code": resp.status_code,
        "json_shape": type(payload).__name__ if payload is not None else "non_json",
    }
    for path in case.get("stable_paths", []):
        signature[f"path:{path}"] = extract_path(payload, path) if payload is not None else None

    return {
        "status_code": resp.status_code,
        "payload": payload,
        "signature": signature,
    }


def signatures_equal(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return a == b


def main() -> int:
    parser = argparse.ArgumentParser(description="Determinism checker")
    parser.add_argument("--url", required=True)
    parser.add_argument("--cases", default="tests/parity/determinism_cases.json")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--report-out", default="tests/parity/determinism_report.json")
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8")).get("cases", [])

    failures: List[Dict[str, Any]] = []

    for case in cases:
        case_id = case["id"]
        repeats = int(case.get("repeats", 5))
        concurrency = int(case.get("concurrency", 8))

        sequential = [make_request(args.url, case, args.timeout) for _ in range(repeats)]
        baseline_sig = sequential[0]["signature"]
        for idx, run in enumerate(sequential[1:], start=2):
            if not signatures_equal(baseline_sig, run["signature"]):
                failures.append(
                    {
                        "case_id": case_id,
                        "phase": "sequential",
                        "run": idx,
                        "expected": baseline_sig,
                        "actual": run["signature"],
                    }
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(make_request, args.url, case, args.timeout) for _ in range(concurrency)]
            concurrent_runs = [f.result() for f in futures]

        for idx, run in enumerate(concurrent_runs, start=1):
            if not signatures_equal(baseline_sig, run["signature"]):
                failures.append(
                    {
                        "case_id": case_id,
                        "phase": "concurrent",
                        "run": idx,
                        "expected": baseline_sig,
                        "actual": run["signature"],
                    }
                )

    report = {
        "cases_total": len(cases),
        "failure_total": len(failures),
        "failures": failures,
    }

    out_path = Path(args.report_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
