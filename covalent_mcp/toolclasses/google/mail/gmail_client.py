"""
Gmail API Client - Wrapper for Gmail operations.

Provides methods for email operations (send, list, get).
"""
from typing import Optional, List, Dict, Any
import logging
import traceback
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
except ImportError:
    raise ImportError("Google API client not installed. Install with: pip install google-api-python-client")

from covalent_mcp.toolclasses.google.gauth import get_credentials_from_db


class GmailService:
    """
    Gmail service wrapper.
    
    Provides methods for sending, listing, and retrieving emails.
    """
    
    def __init__(self, credentials: Optional[Credentials] = None):
        """
        Initialize Gmail service.
        
        Args:
            credentials: Google Credentials object. If not provided, reads from database.
        """
        if credentials is None:
            credentials = get_credentials_from_db()
        
        self.credentials = credentials
        self.service = build('gmail', 'v1', credentials=self.credentials)
    
    def list_messages(
        self,
        query: Optional[str] = None,
        max_results: int = 10,
        label_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        List messages from Gmail.
        
        Args:
            query: Gmail search query (e.g., "from:example@gmail.com", "subject:test")
            max_results: Maximum number of messages to return (1-500)
            label_ids: List of label IDs to filter by (e.g., ["INBOX", "UNREAD"])
        
        Returns:
            List of message metadata dictionaries
        """
        try:
            # Ensure max_results is within limits
            max_results = min(max(1, max_results), 500)
            
            # Prepare request
            request_params = {
                'userId': 'me',
                'maxResults': max_results
            }
            
            if query:
                request_params['q'] = query
            if label_ids:
                request_params['labelIds'] = label_ids
            
            # Execute request
            results = self.service.users().messages().list(**request_params).execute()
            messages = results.get('messages', [])
            
            # Get full message details
            message_list = []
            for msg in messages:
                try:
                    message = self.service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='metadata',
                        metadataHeaders=['From', 'To', 'Subject', 'Date']
                    ).execute()
                    
                    # Extract headers
                    headers = {h['name']: h['value'] for h in message.get('payload', {}).get('headers', [])}
                    
                    message_list.append({
                        'id': message['id'],
                        'threadId': message.get('threadId'),
                        'snippet': message.get('snippet', ''),
                        'from': headers.get('From', ''),
                        'to': headers.get('To', ''),
                        'subject': headers.get('Subject', ''),
                        'date': headers.get('Date', ''),
                        'labelIds': message.get('labelIds', [])
                    })
                except Exception as e:
                    logging.error(f"Error retrieving message {msg.get('id')}: {str(e)}")
                    continue
            
            return message_list
        except Exception as e:
            logging.error(f"Error listing messages: {str(e)}")
            logging.error(traceback.format_exc())
            return []
    
    def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full message details by ID.
        
        Args:
            message_id: Gmail message ID
        
        Returns:
            Message details dictionary or None if not found
        """
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            # Extract headers
            headers = {h['name']: h['value'] for h in message.get('payload', {}).get('headers', [])}
            
            # Extract body
            body = self._extract_body(message.get('payload', {}))
            
            return {
                'id': message['id'],
                'threadId': message.get('threadId'),
                'snippet': message.get('snippet', ''),
                'from': headers.get('From', ''),
                'to': headers.get('To', ''),
                'subject': headers.get('Subject', ''),
                'date': headers.get('Date', ''),
                'body': body,
                'labelIds': message.get('labelIds', [])
            }
        except Exception as e:
            logging.error(f"Error retrieving message {message_id}: {str(e)}")
            logging.error(traceback.format_exc())
            return None
    
    def _extract_body(self, payload: Dict[str, Any]) -> str:
        """Extract message body from payload."""
        body = ""
        
        if 'parts' in payload:
            # Multipart message
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    if data:
                        body += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                elif part['mimeType'] == 'text/html':
                    # Prefer plain text, but use HTML if no plain text
                    if not body:
                        data = part['body'].get('data', '')
                        if data:
                            body += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        else:
            # Single part message
            if payload['mimeType'] == 'text/plain':
                data = payload['body'].get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            elif payload['mimeType'] == 'text/html':
                data = payload['body'].get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        
        return body
    
    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        body_type: str = "text/plain",
        cc: Optional[str] = None,
        bcc: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Send an email message.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body content
            body_type: MIME type ("text/plain" or "text/html")
            cc: CC email address (optional)
            bcc: BCC email address (optional)
        
        Returns:
            Sent message details or None if sending fails
        """
        try:
            # Create message
            if body_type == "text/html":
                message = MIMEMultipart('alternative')
                message.attach(MIMEText(body, 'html'))
            else:
                message = MIMEText(body)
            
            message['to'] = to
            message['subject'] = subject
            if cc:
                message['cc'] = cc
            if bcc:
                message['bcc'] = bcc
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            # Send message
            sent_message = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            return {
                'id': sent_message['id'],
                'threadId': sent_message.get('threadId'),
                'labelIds': sent_message.get('labelIds', [])
            }
        except Exception as e:
            logging.error(f"Error sending message: {str(e)}")
            logging.error(traceback.format_exc())
            return None
