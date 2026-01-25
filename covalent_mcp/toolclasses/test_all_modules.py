"""
Test all MCP tool modules and dump tools + resources schema as JSON.

Spawns the Covalent MCP server via stdio, connects as an MCP client, then:
  1. Lists all tools and resource templates (schema)
  2. Writes schema to mcp_schema.json (default: next to this script)
  3. Optionally runs basic read-only checks from each module

The MCP server exposes tools and resources; their definitions (name, description,
inputSchema for tools; uriTemplate, description for resources) are the "schema"
and are written as JSON. Use that file to integrate with IDEs, clients, or docs.

Run from project root with venv active:
  python -m covalent_mcp.toolclasses.test_all_modules
  python -m covalent_mcp.toolclasses.test_all_modules --schema-only
  python -m covalent_mcp.toolclasses.test_all_modules --schema-out /path/to/schema.json
  python -m covalent_mcp.toolclasses.test_all_modules --connect-url http://127.0.0.1:8000/mcp

By default, the script spawns the server as a subprocess (stdio). Google OAuth may run
on first use (logs go to stderr). Use --connect-url to connect to an already-running
HTTP server instead (e.g. python -m covalent_mcp.server_http).

Exit codes: 0 = all ok, 1 = schema dump or tests failed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Resolve project root: .../covalent_mcp/toolclasses/test_all_modules.py -> .../
_SCRIPT_DIR = Path(__file__).resolve().parent
_COVALENT_MCP = _SCRIPT_DIR.parent
_PROJECT_ROOT = _COVALENT_MCP.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Schema output path (default: next to this script)
DEFAULT_SCHEMA_PATH = _SCRIPT_DIR / "mcp_schema.json"


def _serialize_for_json(obj):
    """Convert MCP types (Pydantic, etc.) to JSON-serializable dicts."""
    if hasattr(obj, "model_dump"):
        d = obj.model_dump(mode="json")
        return {k: _serialize_for_json(v) for k, v in d.items()}
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_for_json(x) for x in obj]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)


async def _run(schema_only: bool, schema_path: Path, connect_url: str | None) -> int:
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport, StreamableHttpTransport

    if connect_url:
        transport = StreamableHttpTransport(connect_url)
    else:
        transport = StdioTransport(
            command=sys.executable,
            args=["-m", "covalent_mcp.server"],
            cwd=str(_PROJECT_ROOT),
            keep_alive=False,
        )
    mcp_client = Client(transport)

    async with mcp_client:
        # --- 1. List tools and resource templates (schema) ---
        print("📋 Listing tools and resource templates...")
        tools = await mcp_client.list_tools()
        templates = await mcp_client.list_resource_templates()

        schema = {
            "tools": [_serialize_for_json(t) for t in tools],
            "resourceTemplates": [_serialize_for_json(r) for r in templates],
        }

        print(f"   Tools: {len(tools)}")
        print(f"   Resource templates: {len(templates)}")

        schema_path = schema_path.resolve()
        schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        print(f"   Schema written to: {schema_path}\n")

        if schema_only:
            return 0

        # --- 2. Basic read-only tests per module ---
        print("🧪 Running basic module checks (read-only)...\n")
        failed = []

        # --- Filesystem: list_directory ---
        try:
            out = await mcp_client.call_tool("list_directory", {"path": "."}, raise_on_error=True)
            data = out.structured_content or {}
            entries = (data.get("entries") or []) if isinstance(data, dict) else []
            print(f"   ✅ Filesystem (list_directory): {len(entries)} entries")
        except Exception as e:
            print(f"   ❌ Filesystem (list_directory): {e}")
            failed.append("filesystem")

        # --- GitHub: read resource github://repo/{owner}/{repo} ---
        try:
            contents = await mcp_client.read_resource(
                "github://repo/KrishivGubba/bballrefapi"
            )
            text = ""
            for c in contents:
                if hasattr(c, "text") and c.text:
                    text = c.text
                    break
            if text:
                data = json.loads(text)
                name = data.get("full_name", "?")
                print(f"   ✅ GitHub (github://repo/...): {name}")
            else:
                print("   ✅ GitHub (github://repo/...): ok (empty)")
        except Exception as e:
            print(f"   ❌ GitHub (github://repo/...): {e}")
            failed.append("github")

        # --- Gmail: read resource gmail://messages?max_results=2 ---
        try:
            contents = await mcp_client.read_resource("gmail://messages?max_results=2")
            text = ""
            for c in contents:
                if hasattr(c, "text") and c.text:
                    text = c.text
                    break
            if text:
                data = json.loads(text)
                n = data.get("count", 0)
                print(f"   ✅ Gmail (gmail://messages): {n} messages")
            else:
                print("   ✅ Gmail (gmail://messages): ok (empty)")
        except Exception as e:
            print(f"   ❌ Gmail (gmail://messages): {e}")
            failed.append("gmail")

        # --- Calendar: read resource google://calendar/{id}/events (need known calendar id) ---
        try:
            # Primary calendar typically has id = user's email
            contents = await mcp_client.read_resource(
                "google://calendar/primary/events"
            )
            text = ""
            for c in contents:
                if hasattr(c, "text") and c.text:
                    text = c.text
                    break
            if text:
                data = json.loads(text)
                n = data.get("count", 0)
                print(f"   ✅ Calendar (google://calendar/primary/events): {n} events")
            else:
                print("   ✅ Calendar (google://calendar/primary/events): ok (empty)")
        except Exception as e:
            print(f"   ❌ Calendar (google://calendar/primary/events): {e}")
            failed.append("calendar")

        # --- Drive: read resource gdrive://folder/root (list root) ---
        try:
            contents = await mcp_client.read_resource("gdrive://folder/root")
            text = ""
            for c in contents:
                if hasattr(c, "text") and c.text:
                    text = c.text
                    break
            if text:
                data = json.loads(text)
                files = data.get("files") or []
                print(f"   ✅ Drive (gdrive://folder/root): {len(files)} items")
            else:
                print("   ✅ Drive (gdrive://folder/root): ok (empty)")
        except Exception as e:
            print(f"   ❌ Drive (gdrive://folder/root): {e}")
            failed.append("drive")

    if failed:
        print(f"\n⚠️  Failed: {', '.join(failed)}")
        return 1
    print("\n✅ All module checks passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test MCP modules and dump tools + resources schema as JSON."
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Only dump schema JSON; skip running tool/resource tests.",
    )
    parser.add_argument(
        "--schema-out",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help=f"Path for schema JSON (default: {DEFAULT_SCHEMA_PATH})",
    )
    parser.add_argument(
        "--connect-url",
        type=str,
        default=None,
        help="Connect to existing HTTP server (e.g. http://127.0.0.1:8000/mcp). "
        "If not set, spawn server via stdio.",
    )
    args = parser.parse_args()

    return asyncio.run(_run(args.schema_only, args.schema_out, args.connect_url))


if __name__ == "__main__":
    sys.exit(main())
