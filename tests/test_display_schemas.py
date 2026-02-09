"""
Test the display schema system across multiple tool types.

Hits /plan_action_direct with various action texts that should trigger
different tools (calendar, email, github, drive, notion, filesystem).
Then validates the 'display' key in the response.

Requires: Flask server + MCP server running.
"""
import requests
import json
import sys

FLASK_URL = "http://localhost:5001"
ENDPOINT = f"{FLASK_URL}/plan_action_direct"

# Each test case: (label, payload)
TEST_CASES = [
    (
        "Calendar — create event",
        {
            "action_text": "Create a calendar event called Team Standup tomorrow at 10am for 30 minutes",
            "context": "",
            "skip_research": True,
        },
    ),
    (
        "Gmail — send email",
        {
            "action_text": "Send an email to john@example.com about the project update",
            "context": "John's email is john@example.com. The project shipped v2.0 yesterday.",
            "skip_research": True,
        },
    ),
    (
        "GitHub — create issue",
        {
            "action_text": "Create a GitHub issue on covalent-calhacks repo about fixing the login bug",
            "context": "Repo owner is krishivgubba, repo name is covalent-calhacks",
            "skip_research": True,
        },
    ),
    (
        "Drive — create file",
        {
            "action_text": "Create a text file called meeting-notes.txt in Google Drive with today's meeting notes",
            "context": "Meeting notes: discussed Q1 roadmap, assigned tasks to team.",
            "skip_research": True,
        },
    ),
    (
        "Notion — create page",
        {
            "action_text": "Create a new Notion page called Sprint Planning with the sprint goals",
            "context": "Sprint goals: ship auth flow, fix calendar sync, deploy to prod.",
            "skip_research": True,
        },
    ),
]


def validate_display(label: str, display: dict | None, proposed_action: dict | None):
    """Check that the display object looks right."""
    issues = []

    if display is None:
        if proposed_action:
            issues.append("display is None but proposed_action exists")
        return issues

    if not display.get("display_name"):
        issues.append("missing display_name")
    if "fields" not in display:
        issues.append("missing fields list")
    elif not isinstance(display["fields"], list) or len(display["fields"]) == 0:
        issues.append("fields is empty or not a list")
    else:
        for f in display["fields"]:
            if not f.get("key"):
                issues.append(f"field missing key: {f}")
            if not f.get("label"):
                issues.append(f"field missing label: {f}")
            if not f.get("widget"):
                issues.append(f"field missing widget: {f}")

    if "has_schema" not in display:
        issues.append("missing has_schema flag")

    return issues


def run_tests():
    passed = 0
    failed = 0

    for label, payload in TEST_CASES:
        print(f"\n{'='*60}")
        print(f"TEST: {label}")
        print(f"{'='*60}")
        print(f"  action_text: {payload['action_text'][:80]}...")

        try:
            resp = requests.post(ENDPOINT, json=payload, timeout=120)
            data = resp.json()

            if resp.status_code != 200 or data.get("status") != "success":
                print(f"  ❌ FAIL — HTTP {resp.status_code}: {data.get('error', 'unknown')}")
                failed += 1
                continue

            proposed = data.get("proposed_action", {})
            display = data.get("display")

            print(f"  Tool chosen:  {proposed.get('tool_name', '???')}")
            print(f"  Parameters:   {json.dumps(proposed.get('parameters', {}), indent=4)}")
            print(f"  has_schema:   {display.get('has_schema') if display else 'N/A'}")
            print(f"  display_name: {display.get('display_name') if display else 'N/A'}")

            if display and display.get("fields"):
                print(f"  fields ({len(display['fields'])}):")
                for f in display["fields"]:
                    val = f.get("value", "—")
                    edit = "✏️" if f.get("editable") else "🔒"
                    print(f"    {edit} [{f['widget']}] {f['label']}: {val}")

            issues = validate_display(label, display, proposed)
            if issues:
                print(f"  ⚠️  Validation issues:")
                for iss in issues:
                    print(f"      - {iss}")
                failed += 1
            else:
                print(f"  ✅ PASS")
                passed += 1

            print(f"  Duration: {data.get('duration_ms', '?')}ms")

        except requests.exceptions.ConnectionError:
            print(f"  ❌ Connection failed — is the Flask server running on {FLASK_URL}?")
            failed += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(TEST_CASES)}")
    print(f"{'='*60}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
