"""
Gmail MCP Tools - Email operations.

Exposes Gmail operations as MCP tools and resources for LLM agents.
Token is managed by the server via OAuth flow - MCP reads token from database.
"""
import json
from typing import Dict, Optional, List
from covalent_mcp.toolclasses.base import (
    MCPToolModule,
    ToolDisplaySchema,
    DisplayField,
    PassableOutput,
)
from covalent_mcp.toolclasses.google.mail.gmail_client import GmailService
from fastmcp import FastMCP


class GmailToolModule(MCPToolModule):
    """
    Gmail tool module for email operations.
    
    Provides MCP tools for:
    - Sending emails
    
    Provides MCP resources for:
    - Listing messages
    - Getting message details
    """
    
    def __init__(self):
        """Initialize Gmail tool module."""
        self._client = None
    
    def _ensure_client(self) -> GmailService:
        """Ensure Gmail client is initialized with fresh credentials from database."""
        # Re-create on every call so token refresh is picked up
        self._client = GmailService()
        return self._client

    def get_display_schemas(self) -> Dict[str, ToolDisplaySchema]:
        """Return display schemas for Gmail tools."""
        return {
            "send_email": ToolDisplaySchema(
                tool_name="send_email",
                display_name="Send Email",
                description="Send an email via Gmail.",
                fields=[
                    DisplayField(key="to", label="To", required=True, widget="text_input", placeholder="recipient@example.com"),
                    DisplayField(key="subject", label="Subject", required=True, widget="text_input"),
                    DisplayField(key="body", label="Body", required=True, widget="textarea", placeholder="Write your message..."),
                    DisplayField(
                        key="body_type", label="Format", widget="select",
                        options=[
                            {"value": "text/plain", "label": "Plain Text"},
                            {"value": "text/html", "label": "HTML"},
                        ],
                    ),
                    DisplayField(key="cc", label="CC", widget="text_input", placeholder="cc@example.com"),
                    DisplayField(key="bcc", label="BCC", widget="text_input", placeholder="bcc@example.com"),
                ],
                passable_outputs=[
                    PassableOutput(key="id", description="The message ID"),
                    PassableOutput(key="threadId", description="The thread ID"),
                ],
            ),
        }
    
    def register(self, mcp: FastMCP) -> None:
        """Register Gmail tools (write operations) with MCP server."""
        tool_module = self
        
        @mcp.tool()
        def send_email(
            to: str,
            subject: str,
            body: str,
            body_type: str = "text/plain",
            cc: Optional[str] = None,
            bcc: Optional[str] = None
        ) -> dict:
            """
            Send an email message.
            
            Args:
                to: Recipient email address
                subject: Email subject line
                body: Email body content
                body_type: MIME type - "text/plain" or "text/html" (default: "text/plain")
                cc: CC email address (optional)
                bcc: BCC email address (optional)
            
            Returns:
                Sent message information including ID and thread ID
            """
            client = tool_module._ensure_client()
            message = client.send_message(
                to=to,
                subject=subject,
                body=body,
                body_type=body_type,
                cc=cc,
                bcc=bcc
            )
            
            if not message:
                return {"success": False, "error": "Failed to send email"}
            
            return {
                "success": True,
                "id": message.get("id"),
                "threadId": message.get("threadId"),
                "message": "Email sent successfully"
            }
    
    def register_resources(self, mcp: FastMCP) -> None:
        """Register Gmail resources (read operations) with MCP server."""
        tool_module = self
        
        @mcp.resource("gmail://messages{?query,max_results,label_ids}")
        def list_messages_resource(
            query: Optional[str] = None,
            max_results: int = 10,
            label_ids: Optional[str] = None
        ) -> str:
            """
            List messages from Gmail.
            
            URI: gmail://messages{?query,max_results,label_ids}
            Optional query params:
            - query: Gmail search query (e.g., "from:example@gmail.com", "subject:test")
            - max_results: Maximum number of messages (1-500, default: 10)
            - label_ids: Comma-separated label IDs (e.g., "INBOX,UNREAD")
            """
            client = tool_module._ensure_client()
            label_list = None
            if label_ids:
                label_list = [l.strip() for l in label_ids.split(',')]
            
            messages = client.list_messages(
                query=query,
                max_results=max_results,
                label_ids=label_list
            )
            
            return json.dumps({
                "count": len(messages),
                "messages": messages
            }, indent=2)
        
        @mcp.resource("gmail://message/{message_id}")
        def get_message_resource(message_id: str) -> str:
            """
            Get full details of a specific message.
            
            URI: gmail://message/{message_id}
            """
            client = tool_module._ensure_client()
            message = client.get_message(message_id)
            if not message:
                return json.dumps({"error": "Message not found"}, indent=2)
            return json.dumps(message, indent=2)


# Create module instance (required for registry pattern)
module = GmailToolModule()
