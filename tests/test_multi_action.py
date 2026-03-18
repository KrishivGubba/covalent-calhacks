"""
Test multi-action chain execution.

Plans an action that requires multiple tools, then executes ALL
proposed actions via the /execute_action chain endpoint.

Requires: FastAPI server + MCP server running.
"""
import os
import requests
import json
import time
import sys

BACKEND_URL = f"http://localhost:{os.environ.get('VITE_FLASK_PORT', '15001')}"

# A multi-step task: create a GitHub issue AND send an email
TASK = {
    "action_text": (
        "can you make a github issue on my basketball reference repo that lists "
        "top 10 facts about lebron james and how the codebase should be dedicated to him. "
        "also email ritesh neela about how i created this and would love for him to check it out."
    ),
    "context": "email of ritesh neela is rneela@wisc.edu",
    "skip_research": False,
}


def fmt(seconds: float) -> str:
    """Format seconds nicely."""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    return f"{seconds:.2f}s"


def run_plan(payload: dict) -> dict | None:
    """Call /plan_action_direct and return the response data."""
    print(f"\n{'='*60}")
    print(f"  PLANNING PHASE")
    print(f"{'='*60}")
    print(f"  action: {payload['action_text'][:80]}...")
    print(f"  skip_research: {payload['skip_research']}")
    print()

    t0 = time.perf_counter()
    try:
        resp = requests.post(
            f"{BACKEND_URL}/plan_action_direct",
            json=payload,
            timeout=180,
        )
    except requests.exceptions.ConnectionError:
        print(f"  ❌ Connection failed — is the server running on {BACKEND_URL}?")
        return None

    elapsed = time.perf_counter() - t0
    data = resp.json()

    if resp.status_code != 200 or data.get("status") != "success":
        print(f"  ❌ FAIL — HTTP {resp.status_code}: {data.get('error')}")
        return None

    server_ms = data.get("duration_ms", 0)
    proposed_actions = data.get("proposed_actions", [])
    displays = data.get("displays", [])
    is_multi = data.get("is_multi_action", False)
    overall = data.get("overall_reasoning", "")

    print(f"  Multi-action: {is_multi}")
    print(f"  Overall reasoning: {overall[:120]}...")
    print(f"  Actions ({len(proposed_actions)}):")
    for i, action in enumerate(proposed_actions):
        display = displays[i] if i < len(displays) else {}
        print(f"    [{action.get('step_id', i+1)}] {action.get('tool_name', '???')}")
        print(f"        Reasoning : {action.get('reasoning', '')[:100]}")
        params = action.get("parameters", {})
        # Show params compactly — truncate long values
        for k, v in params.items():
            val_str = str(v)
            if len(val_str) > 80:
                val_str = val_str[:77] + "..."
            print(f"        {k}: {val_str}")
        print(f"        has_schema: {display.get('has_schema', 'N/A')}")
    print()
    print(f"  ⏱  Server total    : {server_ms}ms")
    print(f"  ⏱  Client round-trip: {fmt(elapsed)}")

    data["_client_elapsed"] = elapsed
    return data


def run_execute_chain(actions: list) -> dict | None:
    """Call /execute_action with the actions array for chain execution."""
    print(f"\n{'='*60}")
    print(f"  CHAIN EXECUTION PHASE ({len(actions)} actions)")
    print(f"{'='*60}")
    for action in actions:
        print(f"    [{action.get('step_id', '?')}] {action.get('tool_name', '???')}")
    print()

    payload = {
        "action_uuid": "",
        "actions": actions,
    }

    t0 = time.perf_counter()
    try:
        resp = requests.post(
            f"{BACKEND_URL}/execute_action",
            json=payload,
            timeout=120,
        )
    except requests.exceptions.ConnectionError:
        print(f"  ❌ Connection failed")
        return None

    elapsed = time.perf_counter() - t0
    data = resp.json()

    overall_status = data.get("status", "unknown")
    summary = data.get("summary", {})
    results = data.get("results", [])
    server_ms = data.get("duration_ms", 0)

    status_icon = {"success": "✅", "partial": "⚠️", "error": "❌"}.get(overall_status, "❓")

    print(f"  {status_icon} Overall: {overall_status}")
    print(f"  Summary: {summary.get('succeeded', 0)}/{summary.get('total', 0)} succeeded, {summary.get('failed', 0)} failed")
    print()

    for result in results:
        step_id = result.get("step_id", "?")
        tool = result.get("tool_name", "???")
        step_status = result.get("status", "unknown")
        icon = "✅" if step_status == "success" else "❌"

        print(f"    {icon} Step {step_id} ({tool}): {step_status}")
        if step_status == "success":
            result_str = str(result.get("result", ""))
            if len(result_str) > 120:
                result_str = result_str[:117] + "..."
            print(f"        Result: {result_str}")
        else:
            print(f"        Error: {result.get('error', 'Unknown')}")

    print()
    print(f"  ⏱  Server total    : {server_ms}ms")
    print(f"  ⏱  Client round-trip: {fmt(elapsed)}")

    data["_client_elapsed"] = elapsed
    return data


def main():
    print("=" * 60)
    print("  MULTI-ACTION CHAIN TEST")
    print("=" * 60)

    # ── Phase 0+1: Research + Planning ────────────────────────
    plan_data = run_plan(TASK)
    if plan_data is None:
        return 1

    proposed_actions = plan_data.get("proposed_actions", [])
    if not proposed_actions:
        print("\n  ❌ No actions proposed — nothing to execute")
        return 1

    is_multi = plan_data.get("is_multi_action", False)
    plan_ms = plan_data.get("duration_ms", 0)

    print(f"\n  📋 {len(proposed_actions)} action(s) proposed (multi={is_multi})")

    # ── Phase 2: Execute ALL actions via chain ────────────────
    exec_data = run_execute_chain(proposed_actions)
    if exec_data is None:
        return 1

    exec_ms = exec_data.get("duration_ms", 0)

    # ── Summary ───────────────────────────────────────────────
    summary = exec_data.get("summary", {})
    total_ms = plan_ms + exec_ms

    print(f"\n\n{'='*60}")
    print(f"  MULTI-ACTION TEST SUMMARY")
    print(f"{'='*60}")
    print()
    print(f"  Actions planned    : {len(proposed_actions)}")
    print(f"  Actions succeeded  : {summary.get('succeeded', 0)}")
    print(f"  Actions failed     : {summary.get('failed', 0)}")
    print()
    print(f"  Planning (server)  : {plan_ms}ms  ({fmt(plan_ms/1000)})")
    print(f"  Execution (server) : {exec_ms}ms  ({fmt(exec_ms/1000)})")
    print(f"  ─────────────────────────────────────")
    print(f"  TOTAL (server)     : {total_ms}ms  ({fmt(total_ms/1000)})")
    print(f"{'='*60}")

    # Return non-zero if any action failed
    if summary.get("failed", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
