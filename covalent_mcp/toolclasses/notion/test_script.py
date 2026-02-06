"""
Test script for Notion MCP tools and resources.

Token is read from the database (integration_tokens table) - no auth flow needed.
Server handles OAuth via /integrations/notion/auth endpoint.

Tests Notion operations in a sequential flow:
1. Get current user info (resource)
2. Search for pages (tool)
3. Create a test page (tool)
4. Get page details (resource)
5. Append content blocks (tool)
6. Get page content (resource)
7. Create a comment (tool)
8. Get comments (resource)
9. Archive the test page (tool)
"""
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
# test_script.py is in: covalent_mcp/toolclasses/notion/
covalent_mcp_dir = Path(__file__).parent.parent.parent  # Gets to covalent_mcp/
project_root = covalent_mcp_dir.parent  # Gets to project root
sys.path.insert(0, str(project_root))

from covalent_mcp.toolclasses.notion.notion_client import NotionClient
from server.integration_dao import IntegrationDAO


def get_notion_client() -> NotionClient:
    """Get a Notion client using the token from the database."""
    db_path = project_root / "context-engine" / "graph.db"
    
    if not db_path.exists():
        raise RuntimeError(f"Database not found at {db_path}")
    
    dao = IntegrationDAO(str(db_path))
    token_data = dao.get_token("notion")
    
    if not token_data:
        raise RuntimeError(
            "Notion is not connected. Please connect Notion from the Integrations page first."
        )
    
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError(
            "Notion token is missing. Please reconnect Notion from the Integrations page."
        )
    
    return NotionClient(access_token=access_token)


# Initialize client - reads token from database automatically
client = get_notion_client()


def test_get_me():
    """Test: Get current bot user info (read-only, safe)."""
    print("=" * 60)
    print("👤 TEST: Get Current User (Resource)")
    print("=" * 60)
    
    me = client.get_me()
    print(f"Bot Name: {me.get('name', 'Unknown')}")
    print(f"Bot ID: {me.get('id')}")
    print(f"Type: {me.get('type')}")
    print()
    
    return me


def test_search(query: str = ""):
    """Test: Search pages and databases (read-only, safe)."""
    print("=" * 60)
    print(f"🔍 TEST: Search Notion (Tool) - query='{query}'")
    print("=" * 60)
    
    results = client.search(query=query, page_size=10)
    items = results.get("results", [])
    
    print(f"Found {len(items)} items\n")
    
    for i, item in enumerate(items[:5], 1):
        obj_type = item.get("object", "unknown")
        title = _extract_title(item)
        print(f"{i}. [{obj_type}] {title}")
        print(f"   ID: {item.get('id')}")
        print(f"   URL: {item.get('url')}")
        print()
    
    return items


def test_get_page(page_id: str):
    """Test: Get page details (read-only, safe)."""
    print("=" * 60)
    print(f"📄 TEST: Get Page (Resource) - {page_id[:20]}...")
    print("=" * 60)
    
    page = client.get_page(page_id)
    
    print(f"Title: {_extract_title(page)}")
    print(f"ID: {page.get('id')}")
    print(f"URL: {page.get('url')}")
    print(f"Created: {page.get('created_time')}")
    print(f"Last edited: {page.get('last_edited_time')}")
    print(f"Archived: {page.get('archived')}")
    print()
    
    return page


def test_get_page_content(page_id: str):
    """Test: Get page content/blocks (read-only, safe)."""
    print("=" * 60)
    print(f"📝 TEST: Get Page Content (Resource) - {page_id[:20]}...")
    print("=" * 60)
    
    result = client.get_block_children(page_id)
    blocks = result.get("results", [])
    
    print(f"Found {len(blocks)} blocks\n")
    
    for i, block in enumerate(blocks[:10], 1):
        block_type = block.get("type", "unknown")
        content = _extract_block_text(block)
        preview = content[:50] + "..." if len(content) > 50 else content
        print(f"{i}. [{block_type}] {preview}")
    
    print()
    return blocks


def test_create_page(parent_page_id: str):
    """Test: Create a new page (creates real page!)."""
    print("=" * 60)
    print("➕ TEST: Create Page (Tool)")
    print("=" * 60)
    
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Build properties
    properties = {
        "title": {
            "title": [{"text": {"content": f"MCP Test Page - {timestamp}"}}]
        }
    }
    
    # Initial content
    children = [
        {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": "This is a test page created via Notion MCP tools."}}]
            }
        },
        {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": f"Created at: {timestamp}"}}]
            }
        }
    ]
    
    page = client.create_page(
        parent_type="page_id",
        parent_id=parent_page_id,
        properties=properties,
        children=children
    )
    
    print(f"✅ Created page: {_extract_title(page)}")
    print(f"   ID: {page.get('id')}")
    print(f"   URL: {page.get('url')}")
    print()
    
    return page


def test_append_blocks(page_id: str):
    """Test: Append content blocks to a page (modifies page!)."""
    print("=" * 60)
    print(f"📝 TEST: Append Blocks (Tool) - {page_id[:20]}...")
    print("=" * 60)
    
    children = [
        {
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Appended Section"}}]
            }
        },
        {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": "This content was appended via the append_block_children API."}}]
            }
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": "First bullet point"}}]
            }
        },
        {
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": "Second bullet point"}}]
            }
        }
    ]
    
    result = client.append_block_children(block_id=page_id, children=children)
    appended = result.get("results", [])
    
    print(f"✅ Appended {len(appended)} blocks")
    print()
    
    return result


def test_create_comment(page_id: str):
    """Test: Create a comment on a page (creates real comment!)."""
    print("=" * 60)
    print(f"💬 TEST: Create Comment (Tool) - {page_id[:20]}...")
    print("=" * 60)
    
    try:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        comment = client.create_comment(
            page_id=page_id,
            content=f"Test comment from MCP tools at {timestamp}"
        )
        
        print(f"✅ Created comment")
        print(f"   ID: {comment.get('id')}")
        print(f"   Created: {comment.get('created_time')}")
        print()
        
        return comment
    except Exception as e:
        print(f"⚠️  Comments not available: {e}")
        print("   (Comments require 'Insert comments' capability in your Notion integration)")
        print()
        return None


def test_get_comments(page_id: str):
    """Test: Get comments on a page (read-only, safe)."""
    print("=" * 60)
    print(f"💬 TEST: Get Comments (Resource) - {page_id[:20]}...")
    print("=" * 60)
    
    try:
        result = client.get_comments(page_id)
        comments = result.get("results", [])
        
        print(f"Found {len(comments)} comments\n")
        
        for i, comment in enumerate(comments[:5], 1):
            text = _extract_rich_text(comment.get("rich_text", []))
            preview = text[:50] + "..." if len(text) > 50 else text
            print(f"{i}. {preview}")
            print(f"   Created: {comment.get('created_time')}")
        
        print()
        return comments
    except Exception as e:
        print(f"⚠️  Could not retrieve comments: {e}")
        print("   (Comments require 'Read comments' capability in your Notion integration)")
        print()
        return None


def test_archive_page(page_id: str):
    """Test: Archive a page (soft delete!)."""
    print("=" * 60)
    print(f"🗑️  TEST: Archive Page (Tool) - {page_id[:20]}...")
    print("=" * 60)
    
    page = client.update_page(page_id=page_id, archived=True)
    
    print(f"✅ Archived page: {page.get('id')}")
    print(f"   Archived: {page.get('archived')}")
    print()
    
    return page


# ============================================================================
# Helper functions
# ============================================================================

def _extract_title(obj):
    """Extract title text from a Notion page or database object."""
    properties = obj.get("properties", {})
    for prop in properties.values():
        if prop.get("type") == "title":
            title_items = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in title_items)
    
    title_array = obj.get("title", [])
    if isinstance(title_array, list) and title_array:
        return "".join(t.get("plain_text", "") for t in title_array)
    
    return "Untitled"


def _extract_rich_text(rich_text):
    """Extract plain text from rich_text array."""
    return "".join(t.get("plain_text", "") for t in rich_text)


def _extract_block_text(block):
    """Extract text content from a block object."""
    block_type = block.get("type", "")
    block_data = block.get(block_type, {})
    
    if "rich_text" in block_data:
        return _extract_rich_text(block_data["rich_text"])
    elif "text" in block_data:
        return _extract_rich_text(block_data["text"])
    
    return ""


# ============================================================================
# Main test flow
# ============================================================================

def main():
    """Run all tests in sequence."""
    print("\n" + "=" * 60)
    print("🚀 NOTION MCP TOOLS - TEST FLOW")
    print("=" * 60 + "\n")
    
    try:
        # STEP 1: Get current user info
        print("STEP 1: Getting current user info...\n")
        me = test_get_me()
        
        # STEP 2: Search for pages
        print("STEP 2: Searching for pages...\n")
        search_results = test_search("")
        
        if not search_results:
            print("❌ No pages found. Make sure the Notion integration has access to some pages.")
            print("   Go to a Notion page → Click '...' → Add connections → Select your integration")
            return
        
        # Find a page we can use as a parent
        parent_page = None
        for item in search_results:
            if item.get("object") == "page":
                parent_page = item
                break
        
        if not parent_page:
            print("❌ No pages found to use as parent. Skipping create/modify tests.")
            return
        
        parent_id = parent_page.get("id")
        print(f"Using parent page: {_extract_title(parent_page)}\n")
        
        # STEP 3: Get parent page details
        print("STEP 3: Getting parent page details...\n")
        test_get_page(parent_id)
        
        # STEP 4: Create a test page
        print("STEP 4: Creating a test page...\n")
        test_page = test_create_page(parent_id)
        
        if not test_page or not test_page.get("id"):
            print("❌ Failed to create test page. Stopping.")
            return
        
        test_page_id = test_page.get("id")
        
        # STEP 5: Get the page we just created
        print("STEP 5: Getting the page we just created...\n")
        test_get_page(test_page_id)
        
        # STEP 6: Append content blocks
        print("STEP 6: Appending content blocks...\n")
        test_append_blocks(test_page_id)
        
        # STEP 7: Get page content
        print("STEP 7: Getting page content...\n")
        test_get_page_content(test_page_id)
        
        # STEP 8: Create a comment (optional - requires comment permissions)
        print("STEP 8: Creating a comment (if permissions allow)...\n")
        test_create_comment(test_page_id)
        
        # STEP 9: Get comments (optional - requires comment permissions)
        print("STEP 9: Getting comments (if permissions allow)...\n")
        test_get_comments(test_page_id)
        
        # STEP 10: Archive the test page (cleanup)
        # Uncomment if you want automatic cleanup
        # print("STEP 10: Archiving test page (cleanup)...\n")
        # test_archive_page(test_page_id)
        
        print("\n" + "=" * 60)
        print("✅ TEST FLOW COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(f"\n📝 Test page created: {test_page.get('url')}")
        print("   You can view it in Notion!")
        print("   (The page was NOT archived - delete it manually if needed)\n")
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ TEST FLOW FAILED")
        print("=" * 60)
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
