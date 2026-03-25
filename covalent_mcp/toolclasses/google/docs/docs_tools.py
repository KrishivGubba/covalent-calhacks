"""
Google Docs MCP Tools - Document read/write, formatting, tables, tabs, and comments.

Exposes Google Docs operations as MCP tools for LLM agents.
Token is managed by the server via OAuth flow - MCP reads token from database.
"""
import sys
from pathlib import Path
from typing import Dict, List, Optional

_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(_project_root))

from covalent_mcp.toolclasses.base import (
    MCPToolModule,
    ToolDisplaySchema,
    DisplayField,
    PassableOutput,
)
from covalent_mcp.toolclasses.google.docs.docs_client import DocsService
from fastmcp import FastMCP


class DocsToolModule(MCPToolModule):
    """
    Google Docs tool module.

    Provides MCP tools for:
    - Reading and writing document content
    - Text insertion, deletion, and find/replace
    - Character and paragraph formatting
    - Table insertion
    - Tab management
    - Comment management
    """

    def __init__(self):
        self._client = None

    def _ensure_client(self) -> DocsService:
        """Re-create client on every call so token refresh is picked up."""
        self._client = DocsService()
        return self._client

    # -------------------------------------------------------------------------
    # Display schemas
    # -------------------------------------------------------------------------

    def get_display_schemas(self) -> Dict[str, ToolDisplaySchema]:
        return {
            "create_document": ToolDisplaySchema(
                tool_name="create_document",
                display_name="Create Google Document",
                description="Create a new blank Google Document.",
                fields=[
                    DisplayField(
                        key="title",
                        label="Document Title",
                        required=True,
                        widget="text_input",
                        placeholder="My Document",
                    )
                ],
                passable_outputs=[
                    PassableOutput(key="id", description="The unique document ID"),
                    PassableOutput(key="name", description="The document title/name"),
                    PassableOutput(key="webViewLink", description="URL to view the document"),
                ],
            ),
            "append_text": ToolDisplaySchema(
                tool_name="append_text",
                display_name="Append Text to Document",
                description="Append text to the end of a Google Document.",
                fields=[
                    DisplayField(
                        key="document_id",
                        label="Document ID",
                        required=True,
                        widget="text_input",
                    ),
                    DisplayField(
                        key="text",
                        label="Text to Append",
                        required=True,
                        widget="textarea",
                    ),
                ],
            ),
            "find_and_replace": ToolDisplaySchema(
                tool_name="find_and_replace",
                display_name="Find and Replace in Document",
                description="Replace all occurrences of text in a Google Document.",
                fields=[
                    DisplayField(
                        key="document_id",
                        label="Document ID",
                        required=True,
                        widget="text_input",
                    ),
                    DisplayField(
                        key="find_text",
                        label="Find",
                        required=True,
                        widget="text_input",
                    ),
                    DisplayField(
                        key="replace_text",
                        label="Replace With",
                        required=True,
                        widget="text_input",
                    ),
                ],
            ),
            "delete_range": ToolDisplaySchema(
                tool_name="delete_range",
                display_name="Delete Range from Document",
                description="Delete a character range from a Google Document.",
                fields=[
                    DisplayField(
                        key="document_id",
                        label="Document ID",
                        required=True,
                        widget="text_input",
                    ),
                    DisplayField(
                        key="start_index",
                        label="Start Index",
                        required=True,
                        widget="text_input",
                    ),
                    DisplayField(
                        key="end_index",
                        label="End Index (exclusive)",
                        required=True,
                        widget="text_input",
                    ),
                ],
            ),
            "add_comment": ToolDisplaySchema(
                tool_name="add_comment",
                display_name="Add Comment to Document",
                description="Add a comment anchored to a text range in a Google Document.",
                fields=[
                    DisplayField(
                        key="document_id",
                        label="Document ID",
                        required=True,
                        widget="text_input",
                    ),
                    DisplayField(
                        key="content",
                        label="Comment Text",
                        required=True,
                        widget="textarea",
                    ),
                    DisplayField(
                        key="start_index",
                        label="Start Index",
                        required=True,
                        widget="text_input",
                    ),
                    DisplayField(
                        key="end_index",
                        label="End Index",
                        required=True,
                        widget="text_input",
                    ),
                ],
                passable_outputs=[
                    PassableOutput(key="id", description="The comment ID (use for replies)"),
                ],
            ),
        }

    # -------------------------------------------------------------------------
    # Tool registration
    # -------------------------------------------------------------------------

    def register(self, mcp: FastMCP) -> None:
        """Register all Google Docs tools with the MCP server."""
        tool_module = self

        # ----- Core -----

        @mcp.tool()
        def read_document(
            document_id: str,
            format: str = "text",
            tab_id: Optional[str] = None,
            max_length: Optional[int] = None,
        ) -> dict:
            """
            Read a Google Document.

            Args:
                document_id: The document ID (from the URL: .../document/d/DOCUMENT_ID/edit)
                format: 'text' (plain text, default), 'json' (raw API structure)
                tab_id: Specific tab ID to read (defaults to first/only tab)
                max_length: Truncate output to this many characters

            Returns:
                Document content as a string inside a dict
            """
            client = tool_module._ensure_client()
            content = client.read_document(document_id, format=format, tab_id=tab_id, max_length=max_length)
            return {"success": True, "content": content}

        @mcp.tool()
        def create_document(title: str) -> dict:
            """
            Create a new blank Google Document.

            Args:
                title: Document title

            Returns:
                Created document info including id and webViewLink
            """
            client = tool_module._ensure_client()
            result = client.create_document(title)
            return {
                "success": True,
                "id": result.get("id"),
                "name": result.get("name"),
                "webViewLink": result.get("webViewLink"),
                "message": f"Created document: {result.get('name')}",
            }

        @mcp.tool()
        def append_text(
            document_id: str,
            text: str,
            add_newline: bool = True,
            tab_id: Optional[str] = None,
        ) -> dict:
            """
            Append text to the end of a Google Document.

            Args:
                document_id: The document ID
                text: Text to append
                add_newline: Prepend a newline before the text (default True)
                tab_id: Specific tab ID (defaults to first tab)

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            client.append_text(document_id, text, add_newline=add_newline, tab_id=tab_id)
            return {"success": True, "message": "Text appended successfully."}

        @mcp.tool()
        def insert_text(
            document_id: str,
            text: str,
            index: int,
            tab_id: Optional[str] = None,
        ) -> dict:
            """
            Insert text at a specific 1-based character index.

            Use read_document with format='json' to determine the correct index.
            Index 1 is the start of the document body.

            Args:
                document_id: The document ID
                text: Text to insert
                index: 1-based character index to insert at
                tab_id: Specific tab ID (defaults to first tab)

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            client.insert_text(document_id, text, index, tab_id=tab_id)
            return {"success": True, "message": f"Text inserted at index {index}."}

        @mcp.tool()
        def delete_range(
            document_id: str,
            start_index: int,
            end_index: int,
            tab_id: Optional[str] = None,
        ) -> dict:
            """
            Delete content within a character range [startIndex, endIndex).

            Args:
                document_id: The document ID
                start_index: Start of range (inclusive, 1-based)
                end_index: End of range (exclusive)
                tab_id: Specific tab ID (defaults to first tab)

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            client.delete_range(document_id, start_index, end_index, tab_id=tab_id)
            return {"success": True, "message": f"Deleted range [{start_index}, {end_index})."}

        @mcp.tool()
        def find_and_replace(
            document_id: str,
            find_text: str,
            replace_text: str,
            match_case: bool = False,
            tab_id: Optional[str] = None,
        ) -> dict:
            """
            Replace all occurrences of text in a document.

            Args:
                document_id: The document ID
                find_text: Text to search for
                replace_text: Text to replace with
                match_case: Case-sensitive matching (default False)
                tab_id: Limit replacements to a specific tab

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            result = client.find_and_replace(
                document_id, find_text, replace_text, match_case=match_case, tab_id=tab_id
            )
            occurrences = (
                result.get("replies", [{}])[0]
                .get("replaceAllText", {})
                .get("occurrencesChanged", 0)
            )
            return {
                "success": True,
                "occurrencesReplaced": occurrences,
                "message": f"Replaced {occurrences} occurrence(s).",
            }

        # ----- Text modification -----

        @mcp.tool()
        def modify_text(
            document_id: str,
            start_index: int,
            end_index: Optional[int] = None,
            text: Optional[str] = None,
            style: Optional[dict] = None,
            tab_id: Optional[str] = None,
        ) -> dict:
            """
            Combined text replacement and/or formatting in one atomic operation.

            Behavior:
            - If end_index + text: deletes [start, end) then inserts text at start
            - If only text: inserts at start_index
            - If style: applies character formatting to the resulting range

            style keys (all optional): bold, italic, underline, strikethrough (bool),
              fontSize (pt), fontFamily (str), foregroundColor ('#RRGGBB'),
              backgroundColor ('#RRGGBB')

            Args:
                document_id: The document ID
                start_index: 1-based start index
                end_index: End index (exclusive) for replacement range
                text: Text to insert or replace with
                style: Character formatting dict
                tab_id: Specific tab ID

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            client.modify_text(
                document_id,
                start_index,
                end_index=end_index,
                text=text,
                style=style,
                tab_id=tab_id,
            )
            return {"success": True, "message": "Text modified successfully."}

        # ----- Formatting -----

        @mcp.tool()
        def apply_text_style(
            document_id: str,
            start_index: int,
            end_index: int,
            style: dict,
            tab_id: Optional[str] = None,
        ) -> dict:
            """
            Apply character-level formatting to a text range.

            style keys (all optional): bold, italic, underline, strikethrough (bool),
              fontSize (number, in points), fontFamily (str),
              foregroundColor ('#RRGGBB'), backgroundColor ('#RRGGBB')

            Args:
                document_id: The document ID
                start_index: Start of range (1-based, inclusive)
                end_index: End of range (exclusive)
                style: Dict of style properties to apply
                tab_id: Specific tab ID

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            client.apply_text_style(document_id, start_index, end_index, style, tab_id=tab_id)
            return {"success": True, "message": "Text style applied."}

        @mcp.tool()
        def apply_paragraph_style(
            document_id: str,
            start_index: int,
            end_index: int,
            style: dict,
            tab_id: Optional[str] = None,
        ) -> dict:
            """
            Apply paragraph-level formatting to a range.

            style keys (all optional):
              alignment: 'START' | 'END' | 'CENTER' | 'JUSTIFIED'
              namedStyleType: 'NORMAL_TEXT' | 'TITLE' | 'HEADING_1' ... 'HEADING_6'
              spaceAbove, spaceBelow (number, in points)
              lineSpacing (number, 100 = single spacing)
              indentFirstLine, indentStart (number, in points)

            Args:
                document_id: The document ID
                start_index: Start of range (1-based, inclusive)
                end_index: End of range (exclusive)
                style: Dict of paragraph style properties
                tab_id: Specific tab ID

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            client.apply_paragraph_style(document_id, start_index, end_index, style, tab_id=tab_id)
            return {"success": True, "message": "Paragraph style applied."}

        # ----- Structure -----

        @mcp.tool()
        def insert_table(
            document_id: str,
            index: int,
            rows: int,
            columns: int,
            tab_id: Optional[str] = None,
        ) -> dict:
            """
            Insert an empty table at a character index.

            Args:
                document_id: The document ID
                index: 1-based character index to insert at
                rows: Number of rows
                columns: Number of columns
                tab_id: Specific tab ID

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            client.insert_table(document_id, index, rows, columns, tab_id=tab_id)
            return {"success": True, "message": f"Inserted {rows}x{columns} table at index {index}."}

        @mcp.tool()
        def insert_table_with_data(
            document_id: str,
            index: int,
            data: List[List[str]],
            has_header_row: bool = False,
            tab_id: Optional[str] = None,
        ) -> dict:
            """
            Insert a pre-populated table at a character index.

            Args:
                document_id: The document ID
                index: 1-based character index to insert at
                data: 2D list of strings (rows x columns)
                has_header_row: Bold the first row as a header (default False)
                tab_id: Specific tab ID

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            client.insert_table_with_data(
                document_id, index, data, has_header_row=has_header_row, tab_id=tab_id
            )
            rows = len(data)
            cols = max(len(r) for r in data) if data else 0
            return {
                "success": True,
                "message": f"Inserted {rows}x{cols} table with data at index {index}.",
            }

        @mcp.tool()
        def insert_page_break(
            document_id: str,
            index: int,
            tab_id: Optional[str] = None,
        ) -> dict:
            """
            Insert a page break at a character index.

            Args:
                document_id: The document ID
                index: 1-based character index to insert at
                tab_id: Specific tab ID

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            client.insert_page_break(document_id, index, tab_id=tab_id)
            return {"success": True, "message": f"Page break inserted at index {index}."}

        # ----- Tabs -----

        @mcp.tool()
        def list_tabs(document_id: str) -> dict:
            """
            List all tabs in a document with their IDs and hierarchy.

            Args:
                document_id: The document ID

            Returns:
                Document title and list of tabs (tabId, title, index, parentTabId)
            """
            client = tool_module._ensure_client()
            return {"success": True, **client.list_tabs(document_id)}

        @mcp.tool()
        def add_tab(
            document_id: str,
            title: Optional[str] = None,
            parent_tab_id: Optional[str] = None,
            index: Optional[int] = None,
        ) -> dict:
            """
            Create a new tab in a document.

            Args:
                document_id: The document ID
                title: Tab title (optional)
                parent_tab_id: ID of parent tab for nesting (optional)
                index: Position index for the new tab (optional)

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            client.add_tab(document_id, title=title, parent_tab_id=parent_tab_id, index=index)
            return {"success": True, "message": f"Tab '{title or 'Untitled'}' created."}

        @mcp.tool()
        def rename_tab(document_id: str, tab_id: str, new_title: str) -> dict:
            """
            Rename an existing tab.

            Args:
                document_id: The document ID
                tab_id: Tab ID (from list_tabs)
                new_title: New tab title

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            client.rename_tab(document_id, tab_id, new_title)
            return {"success": True, "message": f"Tab renamed to '{new_title}'."}

        # ----- Comments -----

        @mcp.tool()
        def list_comments(document_id: str) -> dict:
            """
            List all comments on a document.

            Args:
                document_id: The document ID

            Returns:
                List of comments with id, author, content, quotedText, resolved status
            """
            client = tool_module._ensure_client()
            return {"success": True, **client.list_comments(document_id)}

        @mcp.tool()
        def get_comment(document_id: str, comment_id: str) -> dict:
            """
            Get a specific comment with its full reply thread.

            Args:
                document_id: The document ID
                comment_id: Comment ID (from list_comments)

            Returns:
                Comment with author, content, quotedText, replies
            """
            client = tool_module._ensure_client()
            return {"success": True, **client.get_comment(document_id, comment_id)}

        @mcp.tool()
        def add_comment(
            document_id: str,
            content: str,
            start_index: int,
            end_index: int,
        ) -> dict:
            """
            Add a comment anchored to a text range.

            Note: Comments appear in the comments panel but may not show
            visually anchored to the text in the Google Docs UI due to API limitations.

            Args:
                document_id: The document ID
                content: Comment text
                start_index: Start of anchored range (1-based)
                end_index: End of anchored range (exclusive)

            Returns:
                Created comment id and metadata
            """
            client = tool_module._ensure_client()
            result = client.add_comment(document_id, content, start_index, end_index)
            return {"success": True, **result, "message": "Comment added."}

        @mcp.tool()
        def reply_to_comment(document_id: str, comment_id: str, content: str) -> dict:
            """
            Add a reply to an existing comment thread.

            Args:
                document_id: The document ID
                comment_id: Comment ID to reply to (from list_comments)
                content: Reply text

            Returns:
                Created reply id and metadata
            """
            client = tool_module._ensure_client()
            result = client.reply_to_comment(document_id, comment_id, content)
            return {"success": True, **result, "message": "Reply added."}

        @mcp.tool()
        def resolve_comment(document_id: str, comment_id: str) -> dict:
            """
            Mark a comment as resolved.

            Note: Due to a Google Drive API limitation, the resolved status may not
            visually persist in the Google Docs UI.

            Args:
                document_id: The document ID
                comment_id: Comment ID to resolve (from list_comments)

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            result = client.resolve_comment(document_id, comment_id)
            return {"success": True, **result, "message": "Comment marked as resolved."}

        @mcp.tool()
        def delete_comment(document_id: str, comment_id: str) -> dict:
            """
            Permanently delete a comment and all its replies.

            Args:
                document_id: The document ID
                comment_id: Comment ID to delete (from list_comments)

            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            client.delete_comment(document_id, comment_id)
            return {"success": True, "message": "Comment deleted."}


# Module singleton required for registry pattern
module = DocsToolModule()
