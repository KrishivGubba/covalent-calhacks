#!/usr/bin/env python3
"""
Test script to verify the core AI Gateway models are working:
  1. Claude Sonnet 4.5 (chat)
  2. Claude Haiku 4.5 (chat)
  3. Titan Embed Text V2 (embeddings)

Auth:
    Auto-reads the Auth0 access_token from the local SQLite database
    (context-engine/graph.db) so you don't need to pass --token if
    you've already logged in via the app.

Usage:
    python tests/test_gateway_models.py              # test all 3
    python tests/test_gateway_models.py --health-only
    python tests/test_gateway_models.py --token "jwt" # explicit token
"""

import os
import sys
import time
import argparse

# Add the project root to path so we can import sibling packages
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "llm-interactions"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "server"))

from gateway_client import GatewayClient, GatewayError, MODELS  # noqa: E402
from auth_dao import AuthDAO  # noqa: E402

# Path to the shared SQLite database
DB_PATH = os.path.join(PROJECT_ROOT, "context-engine", "graph.db")

# ── Models under test ────────────────────────────────────────────────
CHAT_MODELS = {
    "claude-4.5-sonnet": MODELS["claude-4.5-sonnet"],
    "claude-4.5-haiku": MODELS["claude-4.5-haiku"],
}
EMBEDDING_MODEL_ALIAS = "titan-embed-v2"
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"

# Tiny prompt for chat tests – one-word answer keeps cost minimal
CHAT_PROMPT = "Reply with only the word 'ok'."
CHAT_MAX_TOKENS = 16


# ── Helpers ──────────────────────────────────────────────────────────
def load_token_from_db() -> str | None:
    """Try to read an Auth0 access_token from the local SQLite database."""
    db = os.path.realpath(DB_PATH)
    if not os.path.exists(db):
        print(f"  DB not found at {db} – cannot auto-load token")
        return None

    try:
        dao = AuthDAO(db)
        sessions = dao.get_all_sessions()
        if not sessions:
            print("  No active sessions in the database")
            return None

        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        user_id = sessions[0]["user_id"]
        session = dao.get_session(user_id)
        if not session or not session.get("access_token"):
            print(f"  Session for {user_id} has no access_token")
            return None

        print(f"  Loaded token for user: {user_id}")
        print(f"  Session updated at:    {session.get('updated_at', '?')}")
        return session["access_token"]
    except Exception as e:
        print(f"  Failed to read token from DB: {e}")
        return None


def test_health(client: GatewayClient) -> dict:
    """Test the /health endpoint (no auth required)."""
    print("\n--- Health Check ---")
    try:
        data = client.health()
        print(f"  Status:        {data.get('status')}")
        print(f"  Region:        {data.get('region')}")
        print(f"  Default model: {data.get('default_model')}")
        return {"success": True, "data": data}
    except GatewayError as e:
        print(f"  FAIL: {e} (HTTP {e.status_code})")
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"  FAIL: {e}")
        return {"success": False, "error": str(e)}


def test_chat_model(client: GatewayClient, alias: str, model_id: str) -> dict:
    """Send a small chat prompt to a model and report the result."""
    print(f"\n  [{alias}]  {model_id}")
    start = time.time()
    try:
        response = client.generate(
            prompt=CHAT_PROMPT,
            model=model_id,
            max_tokens=CHAT_MAX_TOKENS,
            temperature=0.0,
        )
        elapsed = time.time() - start
        preview = response.content.strip()[:80]
        print(f"    PASS  ({elapsed:.1f}s)  tokens: {response.input_tokens} -> {response.output_tokens}  "
              f"stop: {response.stop_reason}")
        print(f"    Response: {preview}")
        return {"success": True, "alias": alias, "model_id": model_id, "elapsed_s": round(elapsed, 2)}
    except GatewayError as e:
        elapsed = time.time() - start
        print(f"    FAIL  ({elapsed:.1f}s)  HTTP {e.status_code}: {e.message[:120]}")
        return {"success": False, "alias": alias, "model_id": model_id,
                "error": e.message, "status_code": e.status_code, "elapsed_s": round(elapsed, 2)}
    except Exception as e:
        elapsed = time.time() - start
        print(f"    FAIL  ({elapsed:.1f}s)  {e}")
        return {"success": False, "alias": alias, "model_id": model_id,
                "error": str(e), "elapsed_s": round(elapsed, 2)}


def test_embedding(client: GatewayClient) -> dict:
    """Test the /embed endpoint with Titan Embed V2."""
    print(f"\n  [{EMBEDDING_MODEL_ALIAS}]  {EMBEDDING_MODEL_ID}")
    start = time.time()
    try:
        response = client.embed(text="Hello world, this is a test embedding.")
        elapsed = time.time() - start
        dims = len(response.embedding)
        print(f"    PASS  ({elapsed:.1f}s)  dims: {dims}  tokens: {response.input_tokens}")
        print(f"    First 5 values: {response.embedding[:5]}")
        return {"success": True, "alias": EMBEDDING_MODEL_ALIAS,
                "model_id": EMBEDDING_MODEL_ID, "dims": dims, "elapsed_s": round(elapsed, 2)}
    except GatewayError as e:
        elapsed = time.time() - start
        print(f"    FAIL  ({elapsed:.1f}s)  HTTP {e.status_code}: {e.message[:120]}")
        return {"success": False, "alias": EMBEDDING_MODEL_ALIAS, "model_id": EMBEDDING_MODEL_ID,
                "error": e.message, "status_code": e.status_code, "elapsed_s": round(elapsed, 2)}
    except Exception as e:
        elapsed = time.time() - start
        print(f"    FAIL  ({elapsed:.1f}s)  {e}")
        return {"success": False, "alias": EMBEDDING_MODEL_ALIAS, "model_id": EMBEDDING_MODEL_ID,
                "error": str(e), "elapsed_s": round(elapsed, 2)}


# ── Main ─────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Test core AI Gateway models")
    parser.add_argument("--url", default=None,
                        help="Gateway URL (default: GATEWAY_URL env var)")
    parser.add_argument("--token", default=None,
                        help="Auth0 JWT token (auto-loaded from DB if omitted)")
    parser.add_argument("--health-only", action="store_true",
                        help="Only run the health check")
    args = parser.parse_args()

    # ── Resolve auth token ───────────────────────────────────────────
    token = args.token
    if not token:
        print("\n  No --token flag; trying to load from local DB...")
        token = load_token_from_db()
        if not token:
            print("  Could not auto-load token. Pass --token or log in via the app first.")

    # Build client
    try:
        client = GatewayClient(url=args.url, access_token=token, timeout=90)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print("=" * 64)
    print("AI Gateway – Core Model Tests")
    print("=" * 64)
    print(f"  Gateway: {client.url}")

    # ── Health ───────────────────────────────────────────────────────
    health = test_health(client)
    if not health["success"]:
        print("\nHealth check failed – is the Lambda deployed?")
        return 1

    if args.health_only:
        print("\n(Skipping model tests)")
        return 0

    if not token:
        print("\n  No token available – cannot test models.")
        print("  Pass --token or log in via the app first.")
        return 1

    # ── Run model tests ──────────────────────────────────────────────
    print("\n--- Chat Models ---")
    results: list[dict] = []
    for alias, model_id in CHAT_MODELS.items():
        results.append(test_chat_model(client, alias, model_id))

    print("\n--- Embedding Model ---")
    results.append(test_embedding(client))

    # ── Summary ──────────────────────────────────────────────────────
    passed = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    print("\n" + "=" * 64)
    print("Summary")
    print("=" * 64)
    print(f"\n  {len(passed)}/{len(results)} models passed")

    if passed:
        total_time = sum(r["elapsed_s"] for r in passed)
        print(f"  Total time (passing): {total_time:.1f}s")

    if failed:
        print("\n  Failed:")
        for r in failed:
            print(f"    - {r['alias']}  ({r['model_id']})")
            print(f"      {r.get('error', 'unknown error')}")

    print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
