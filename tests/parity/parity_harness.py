#!/usr/bin/env python3
"""
Flask-vs-FastAPI parity harness.

Compares status codes, JSON shape, selected key values, and optional side effects
for a golden request corpus.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


MISSING = object()


@dataclass
class Mismatch:
    case_id: str
    kind: str
    message: str
    path: Optional[str] = None
    flask_value: Any = None
    fastapi_value: Any = None


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_json_response(resp: requests.Response) -> Dict[str, Any]:
    content_type = (resp.headers.get("Content-Type") or "").lower()
    parsed_json = None
    if "application/json" in content_type:
        try:
            parsed_json = resp.json()
        except Exception:
            parsed_json = None
    else:
        try:
            parsed_json = resp.json()
        except Exception:
            parsed_json = None

    return {
        "status_code": resp.status_code,
        "headers": {k: v for k, v in resp.headers.items()},
        "json": parsed_json,
        "text": resp.text,
    }


def request_case(base_url: str, case: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
    method = case.get("method", "GET").upper()
    path = case["path"]
    url = f"{base_url.rstrip('/')}{path}"
    query = case.get("query")
    body = case.get("body")

    resp = requests.request(
        method=method,
        url=url,
        params=query,
        json=body,
        timeout=timeout_s,
    )
    return parse_json_response(resp)


def shape_of(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: shape_of(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        if not value:
            return ["<empty>"]
        return [shape_of(value[0])]
    return type(value).__name__


def _tokenize_path(path: str) -> List[tuple[str, Optional[str]]]:
    parts = []
    for token in path.split("."):
        m = re.fullmatch(r"([^\[\]]+)(?:\[(\*|\d+)\])?", token)
        if not m:
            parts.append((token, None))
        else:
            parts.append((m.group(1), m.group(2)))
    return parts


def extract_path(data: Any, path: str) -> Any:
    current = data
    for key, index in _tokenize_path(path):
        if not isinstance(current, dict) or key not in current:
            return MISSING
        current = current[key]

        if index is None:
            continue

        if not isinstance(current, list):
            return MISSING
        if index == "*":
            return current
        idx = int(index)
        if idx < 0 or idx >= len(current):
            return MISSING
        current = current[idx]

    return current


def load_allowlist(path: Optional[Path]) -> List[Dict[str, Any]]:
    if not path:
        return []
    data = load_json(path)
    return data.get("allowed_mismatches", [])


def is_allowed(mismatch: Mismatch, allowlist: List[Dict[str, Any]]) -> bool:
    for rule in allowlist:
        if rule.get("case_id") != mismatch.case_id:
            continue
        if rule.get("kind") != mismatch.kind:
            continue
        rule_path = rule.get("path")
        if rule_path is not None and rule_path != mismatch.path:
            continue
        return True
    return False


def coerce_numeric(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def probe_side_effect(base_url: str, probe: Dict[str, Any], timeout_s: float) -> Any:
    probe_case = {
        "method": probe.get("method", "GET"),
        "path": probe["path"],
        "query": probe.get("query"),
        "body": probe.get("body"),
    }
    result = request_case(base_url, probe_case, timeout_s)
    path = probe.get("value_path")
    if not path:
        return result
    payload = result.get("json")
    if payload is None:
        return MISSING
    return extract_path(payload, path)


def compare(
    case: Dict[str, Any],
    flask_result: Dict[str, Any],
    fastapi_result: Dict[str, Any],
) -> List[Mismatch]:
    mismatches: List[Mismatch] = []
    case_id = case["id"]
    compare_shape = case.get("compare_json_shape", True)

    if flask_result["status_code"] != fastapi_result["status_code"]:
        mismatches.append(
            Mismatch(
                case_id=case_id,
                kind="status_code",
                message="HTTP status code mismatch",
                flask_value=flask_result["status_code"],
                fastapi_value=fastapi_result["status_code"],
            )
        )

    flask_json = flask_result.get("json")
    fastapi_json = fastapi_result.get("json")

    if (flask_json is None) != (fastapi_json is None):
        mismatches.append(
            Mismatch(
                case_id=case_id,
                kind="response_type",
                message="JSON parseability mismatch",
                flask_value=flask_json,
                fastapi_value=fastapi_json,
            )
        )
        return mismatches

    if flask_json is not None and fastapi_json is not None:
        if compare_shape:
            flask_shape = shape_of(flask_json)
            fastapi_shape = shape_of(fastapi_json)
            if flask_shape != fastapi_shape:
                mismatches.append(
                    Mismatch(
                        case_id=case_id,
                        kind="json_shape",
                        message="JSON shape mismatch",
                        flask_value=flask_shape,
                        fastapi_value=fastapi_shape,
                    )
                )

        for path in case.get("must_match_paths", []):
            f_value = extract_path(flask_json, path)
            a_value = extract_path(fastapi_json, path)
            if f_value is MISSING or a_value is MISSING or f_value != a_value:
                mismatches.append(
                    Mismatch(
                        case_id=case_id,
                        kind="path_value",
                        path=path,
                        message=f"Value mismatch at '{path}'",
                        flask_value=None if f_value is MISSING else f_value,
                        fastapi_value=None if a_value is MISSING else a_value,
                    )
                )
    else:
        if flask_result.get("text") != fastapi_result.get("text"):
            mismatches.append(
                Mismatch(
                    case_id=case_id,
                    kind="text_body",
                    message="Text response mismatch",
                    flask_value=flask_result.get("text"),
                    fastapi_value=fastapi_result.get("text"),
                )
            )

    return mismatches


def run_harness(
    flask_url: Optional[str],
    fastapi_url: str,
    corpus: List[Dict[str, Any]],
    allowlist: List[Dict[str, Any]],
    timeout_s: float,
    snapshot_in: Optional[Path] = None,
    snapshot_out: Optional[Path] = None,
) -> Dict[str, Any]:
    snapshot_data: Dict[str, Any] = {"cases": {}}
    baseline_cases: Dict[str, Any] = {}

    if snapshot_in:
        snapshot_payload = load_json(snapshot_in)
        baseline_cases = snapshot_payload.get("cases", {})
    elif flask_url:
        baseline_cases = {}
    else:
        raise ValueError("Either --flask-url or --snapshot-in must be provided")

    all_mismatches: List[Mismatch] = []
    approved_mismatches: List[Mismatch] = []
    unapproved_mismatches: List[Mismatch] = []

    for case in corpus:
        case_id = case["id"]

        if snapshot_in:
            flask_result = baseline_cases.get(case_id)
            if flask_result is None:
                raise ValueError(f"Case '{case_id}' missing in snapshot file")
        else:
            flask_result = request_case(flask_url, case, timeout_s)

        fastapi_result = request_case(fastapi_url, case, timeout_s)

        if snapshot_out is not None and not snapshot_in:
            snapshot_data["cases"][case_id] = flask_result

        mismatches = compare(case, flask_result, fastapi_result)

        side_effect = case.get("side_effect_check")
        if side_effect:
            if snapshot_in:
                # Side-effect checks require live Flask baseline.
                pass
            else:
                flask_before = probe_side_effect(flask_url, side_effect, timeout_s)
                fastapi_before = probe_side_effect(fastapi_url, side_effect, timeout_s)

                _ = request_case(flask_url, case, timeout_s)
                _ = request_case(fastapi_url, case, timeout_s)

                flask_after = probe_side_effect(flask_url, side_effect, timeout_s)
                fastapi_after = probe_side_effect(fastapi_url, side_effect, timeout_s)

                fb = coerce_numeric(flask_before)
                fa = coerce_numeric(flask_after)
                ab = coerce_numeric(fastapi_before)
                aa = coerce_numeric(fastapi_after)

                if None not in (fb, fa, ab, aa):
                    flask_delta = fa - fb
                    fastapi_delta = aa - ab
                    if flask_delta != fastapi_delta:
                        mismatches.append(
                            Mismatch(
                                case_id=case_id,
                                kind="side_effect_delta",
                                message="Side-effect delta mismatch",
                                path=side_effect.get("value_path"),
                                flask_value=flask_delta,
                                fastapi_value=fastapi_delta,
                            )
                        )

                    expected_delta = side_effect.get("expected_delta")
                    if expected_delta is not None and fastapi_delta != expected_delta:
                        mismatches.append(
                            Mismatch(
                                case_id=case_id,
                                kind="side_effect_expected",
                                message="FastAPI side-effect delta deviates from expected",
                                path=side_effect.get("value_path"),
                                flask_value=expected_delta,
                                fastapi_value=fastapi_delta,
                            )
                        )

        for mismatch in mismatches:
            all_mismatches.append(mismatch)
            if is_allowed(mismatch, allowlist):
                approved_mismatches.append(mismatch)
            else:
                unapproved_mismatches.append(mismatch)

    if snapshot_out is not None and not snapshot_in:
        snapshot_out.parent.mkdir(parents=True, exist_ok=True)
        with snapshot_out.open("w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2)

    return {
        "cases_total": len(corpus),
        "mismatch_total": len(all_mismatches),
        "approved_mismatch_total": len(approved_mismatches),
        "unapproved_mismatch_total": len(unapproved_mismatches),
        "mismatches": [asdict(m) for m in all_mismatches],
        "approved_mismatches": [asdict(m) for m in approved_mismatches],
        "unapproved_mismatches": [asdict(m) for m in unapproved_mismatches],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Flask/FastAPI parity harness")
    parser.add_argument("--flask-url", default=None, help="Flask baseline URL (example: http://127.0.0.1:15001)")
    parser.add_argument("--fastapi-url", required=True, help="FastAPI candidate URL (example: http://127.0.0.1:15002)")
    parser.add_argument(
        "--corpus",
        default="tests/parity/golden_corpus.json",
        help="Path to corpus JSON",
    )
    parser.add_argument(
        "--allowlist",
        default="tests/parity/allowlist.json",
        help="Path to allowlist JSON",
    )
    parser.add_argument(
        "--snapshot-in",
        default=None,
        help="Path to frozen Flask snapshot JSON (if provided, Flask URL is optional)",
    )
    parser.add_argument(
        "--snapshot-out",
        default=None,
        help="Write Flask baseline snapshot JSON to this path",
    )
    parser.add_argument(
        "--report-out",
        default="tests/parity/last_report.json",
        help="Write harness report JSON to this path",
    )
    parser.add_argument("--timeout", type=float, default=10.0)

    args = parser.parse_args()

    corpus = load_json(Path(args.corpus)).get("cases", [])
    allowlist = load_allowlist(Path(args.allowlist) if args.allowlist else None)

    report = run_harness(
        flask_url=args.flask_url,
        fastapi_url=args.fastapi_url,
        corpus=corpus,
        allowlist=allowlist,
        timeout_s=args.timeout,
        snapshot_in=Path(args.snapshot_in) if args.snapshot_in else None,
        snapshot_out=Path(args.snapshot_out) if args.snapshot_out else None,
    )

    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    with report_out.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(
        "Parity report:",
        f"cases={report['cases_total']}",
        f"mismatches={report['mismatch_total']}",
        f"approved={report['approved_mismatch_total']}",
        f"unapproved={report['unapproved_mismatch_total']}",
    )

    if report["unapproved_mismatch_total"] > 0:
        print("Unapproved mismatches:")
        for m in report["unapproved_mismatches"]:
            path = f" path={m['path']}" if m.get("path") else ""
            print(f"- [{m['case_id']}] {m['kind']}{path}: {m['message']}")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
