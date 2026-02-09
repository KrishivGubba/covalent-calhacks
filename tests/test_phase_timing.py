"""
Time every phase of the action execution flow.

Runs a full end-to-end flow:
  1. Research phase  (gather context via read-only resources)
  2. Planning phase  (LLM proposes a tool call)
  3. Display resolve (resolve display schema for approval UI)
  4. Execution phase (actually run the tool)

Uses a safe filesystem write_file action so execution doesn't
touch any external APIs (no emails sent, no events created).

Requires: Flask server + MCP server running.
"""
import requests
import json
import time
import sys

FLASK_URL = "http://localhost:5001"

# A task that triggers research (skip_research=False) and results in
# a filesystem write_file tool call — safe to actually execute.
TASK = {
    "action_text": "Create a text file called test_timing_output.txt with a summary of today's tech news",
    "context": "Save the file in the current directory. Keep it short, 2-3 sentences.",
    "skip_research": False,
}

# Also test with skip_research=True so we can isolate planning time
TASK_NO_RESEARCH = {
    "action_text": "Create a text file called test_timing_output.txt with a summary of today's tech news",
    "context": "Save the file in the current directory. Keep it short, 2-3 sentences.",
    "skip_research": True,
}


def fmt(seconds: float) -> str:
    """Format seconds nicely."""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    return f"{seconds:.2f}s"


def run_plan(label: str, payload: dict) -> dict | None:
    """Call /plan_action_direct and return the response data."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  action: {payload['action_text'][:70]}...")
    print(f"  skip_research: {payload['skip_research']}")
    print()

    t0 = time.perf_counter()
    try:
        resp = requests.post(
            f"{FLASK_URL}/plan_action_direct",
            json=payload,
            timeout=180,
        )
    except requests.exceptions.ConnectionError:
        print(f"  ❌ Connection failed — is the Flask server running on {FLASK_URL}?")
        return None

    elapsed = time.perf_counter() - t0
    data = resp.json()

    if resp.status_code != 200 or data.get("status") != "success":
        print(f"  ❌ FAIL — HTTP {resp.status_code}: {data.get('error')}")
        return None

    server_total_ms = data.get("duration_ms", 0)
    proposed = data.get("proposed_action", {})
    display = data.get("display")

    print(f"  Tool chosen : {proposed.get('tool_name', '???')}")
    print(f"  Params      : {json.dumps(proposed.get('parameters', {}), indent=4)}")
    print(f"  has_schema  : {display.get('has_schema') if display else 'N/A'}")
    print()
    print(f"  ⏱  Server total    : {server_total_ms}ms")
    print(f"  ⏱  Client round-trip: {fmt(elapsed)}")

    data["_client_elapsed"] = elapsed
    return data


def run_execute(tool_name: str, parameters: dict) -> dict | None:
    """Call /execute_action and return the response data."""
    print(f"\n{'='*60}")
    print(f"  EXECUTION PHASE")
    print(f"{'='*60}")
    print(f"  tool: {tool_name}")
    print()

    payload = {
        "action_uuid": "",
        "tool_name": tool_name,
        "parameters": parameters,
    }

    t0 = time.perf_counter()
    try:
        resp = requests.post(
            f"{FLASK_URL}/execute_action",
            json=payload,
            timeout=60,
        )
    except requests.exceptions.ConnectionError:
        print(f"  ❌ Connection failed")
        return None

    elapsed = time.perf_counter() - t0
    data = resp.json()

    status = "✅" if data.get("status") == "success" else "❌"
    server_ms = data.get("duration_ms", 0)

    print(f"  {status} Status: {data.get('status')}")
    if data.get("error"):
        print(f"     Error: {data['error']}")
    print()
    print(f"  ⏱  Server total    : {server_ms}ms")
    print(f"  ⏱  Client round-trip: {fmt(elapsed)}")

    data["_client_elapsed"] = elapsed
    return data


def main():
    print("=" * 60)
    print("  PHASE TIMING TEST")
    print("=" * 60)

    # ── Run 1: Full flow (research + planning) ──────────────────
    full = run_plan("RUN 1: RESEARCH + PLANNING", TASK)
    if full is None:
        return 1

    # ── Run 2: Planning only (skip research) ────────────────────
    plan_only = run_plan("RUN 2: PLANNING ONLY (skip research)", TASK_NO_RESEARCH)
    if plan_only is None:
        return 1

    # ── Derive research time ────────────────────────────────────
    full_ms = full.get("duration_ms", 0)
    plan_ms = plan_only.get("duration_ms", 0)
    research_ms = max(full_ms - plan_ms, 0)

    # ── Run 3: Execute the planned action ───────────────────────
    proposed = full.get("proposed_action") or plan_only.get("proposed_action", {})
    tool_name = proposed.get("tool_name", "")
    params = proposed.get("parameters", {})

    exec_result = None
    if tool_name and params:
        exec_result = run_execute(tool_name, params)
    else:
        print("\n  ⚠️  No proposed action to execute")

    # ── Summary ─────────────────────────────────────────────────
    print(f"\n\n{'='*60}")
    print(f"  TIMING SUMMARY")
    print(f"{'='*60}")
    print()
    print(f"  Research + Planning (server) : {full_ms}ms  ({fmt(full_ms/1000)})")
    print(f"  Planning only (server)       : {plan_ms}ms  ({fmt(plan_ms/1000)})")
    print(f"  Research phase (derived)     : ~{research_ms}ms  ({fmt(research_ms/1000)})")
    print()
    if exec_result:
        exec_ms = exec_result.get("duration_ms", 0)
        print(f"  Execution (server)           : {exec_ms}ms  ({fmt(exec_ms/1000)})")
        total = full_ms + exec_ms
        print()
        print(f"  ─────────────────────────────────────")
        print(f"  TOTAL end-to-end (server)    : {total}ms  ({fmt(total/1000)})")
        print()
        print(f"  Breakdown:")
        print(f"    Research : {research_ms:>6}ms  ({research_ms*100/total:.0f}%)" if total > 0 else "")
        print(f"    Planning : {plan_ms:>6}ms  ({plan_ms*100/total:.0f}%)" if total > 0 else "")
        print(f"    Execution: {exec_ms:>6}ms  ({exec_ms*100/total:.0f}%)" if total > 0 else "")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
