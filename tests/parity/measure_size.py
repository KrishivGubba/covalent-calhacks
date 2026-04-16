#!/usr/bin/env python3
"""
Measure packaged server footprint for release gating.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def bytes_to_mb(num_bytes: int) -> float:
    return round(num_bytes / (1024 * 1024), 2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure server bundle size")
    parser.add_argument("--dist-servers", default="dist-servers")
    parser.add_argument("--tauri-servers", default="src-tauri/servers")
    parser.add_argument("--baseline-json", default=None, help="Optional baseline JSON from previous run")
    parser.add_argument("--out", default="tests/parity/size_report.json")
    args = parser.parse_args()

    dist_path = Path(args.dist_servers)
    tauri_path = Path(args.tauri_servers)

    report = {
        "dist_servers_bytes": dir_size_bytes(dist_path),
        "dist_servers_mb": bytes_to_mb(dir_size_bytes(dist_path)),
        "tauri_servers_bytes": dir_size_bytes(tauri_path),
        "tauri_servers_mb": bytes_to_mb(dir_size_bytes(tauri_path)),
    }

    if args.baseline_json:
        baseline_path = Path(args.baseline_json)
        if baseline_path.exists():
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            report["delta_dist_servers_bytes"] = report["dist_servers_bytes"] - baseline.get("dist_servers_bytes", 0)
            report["delta_tauri_servers_bytes"] = report["tauri_servers_bytes"] - baseline.get("tauri_servers_bytes", 0)
            report["delta_dist_servers_mb"] = bytes_to_mb(report["delta_dist_servers_bytes"])
            report["delta_tauri_servers_mb"] = bytes_to_mb(report["delta_tauri_servers_bytes"])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
