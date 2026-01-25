"""
Gmail MCP Tools - Email operations.

Exposes Gmail operations as MCP tools and resources for LLM agents.
"""
import json
from typing import Optional, List
from covalent_mcp.toolclasses.base import MCPToolModule
from covalent_mcp.toolclasses.google.mail.gmail_client import GmailService
from covalent_mcp.toolclasses.google.gauth import GoogleAuth, DEFAULT_SCOPES
from fastmcp import FastMCP


class GmailToolModule(MCPToolModule):
    """
    Gmail tool module for email operations.
    
    Provides MCP tools for:
    - Sending emails ✅
    
    Provides MCP resources for:
    - Listing messages ✅
    - Getting message details ✅
    """
    
    def __init__(self):
        """Initialize Gmail tool module with auth and client."""
        self.auth = None  # Lazy initialization
        self.client = None
    
    def _ensure_client(self) -> GmailService:
        """Ensure Gmail client is initialized."""
        if self.client is None:
            # Use DEFAULT_SCOPES to include both Calendar and Gmail scopes
            self.auth = GoogleAuth(scopes=DEFAULT_SCOPES)
            self.client = GmailService(auth=self.auth)
        return self.client
    
    def register(self, mcp: FastMCP) -> None:
        """Register Gmail tools (write operations) with MCP server."""
        client = self._ensure_client()
        
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
        client = self._ensure_client()
        
        @mcp.resource("gmail://messages")
        def list_messages_resource(
            query: Optional[str] = None,
            max_results: int = 10,
            label_ids: Optional[str] = None
        ) -> str:
            """
            List messages from Gmail.
            
            URI: gmail://messages
            Optional query params:
            - query: Gmail search query (e.g., "from:example@gmail.com", "subject:test")
            - max_results: Maximum number of messages (1-500, default: 10)
            - label_ids: Comma-separated label IDs (e.g., "INBOX,UNREAD")
            """
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
            message = client.get_message(message_id)
            if not message:
                return json.dumps({"error": "Message not found"}, indent=2)
            return json.dumps(message, indent=2)


# Create module instance (required for registry pattern)
module = GmailToolModule()
