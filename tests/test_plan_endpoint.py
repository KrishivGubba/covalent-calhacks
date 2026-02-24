"""
Test the /plan_action endpoint.

NOTE: The /plan_action endpoint requires a real action_uuid from the database.
This test uses /plan_action_direct which accepts raw action_text and context.
"""
import os
import requests
import json

FLASK_URL = f"http://localhost:{os.environ.get('VITE_FLASK_PORT', '15001')}"


def test_plan_action_direct():
    """Test the plan_action_direct endpoint with raw action text."""
    
    payload = {
        "action_text": "Send an email to ritesh about the latest tech news",
        "context": "Ritesh's email is ritesh@example.com",
        "skip_research": False
    }
    
    print(f"🔄 Calling {FLASK_URL}/plan_action_direct")
    print(f"📤 Payload: {json.dumps(payload, indent=2)}")
    print()
    
    try:
        response = requests.post(
            f"{FLASK_URL}/plan_action_direct",
            json=payload,
            timeout=120  # LLM calls can take a while
        )
        
        print(f"📥 Status: {response.status_code}")
        print(f"📥 Response:")
        print(json.dumps(response.json(), indent=2))
        
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - is the Flask server running?")
        print("   Run: ./server/start_server.sh")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    test_plan_action_direct()
