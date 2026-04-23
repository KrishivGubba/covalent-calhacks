"""
Google Drive API Client - Wrapper for Drive operations.

Provides methods for file and folder operations.
"""
from typing import Optional, List, Dict, Any
import logging
import traceback
import base64
from io import BytesIO

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from googleapiclient.http import MediaIoBaseUpload
except ImportError:
    raise ImportError("Google API client not installed. Install with: pip install google-api-python-client")

from covalent_mcp.toolclasses.google.gauth import get_credentials_from_db


# Constants
FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'
TEXT_MIME_TYPES = {
    'txt': 'text/plain',
    'md': 'text/markdown',
    'json': 'application/json',
}


class DriveService:
    """
    Google Drive service wrapper.
    
    Provides methods for file and folder operations.
    """
    
    def __init__(self, credentials: Optional[Credentials] = None):
        """
        Initialize Drive service.
        
        Args:
            credentials: Google Credentials object. If not provided, reads from database.
        """
        if credentials is None:
            credentials = get_credentials_from_db()
        
        self.credentials = credentials
        self.service = build('drive', 'v3', credentials=self.credentials)
    
    def search_files(
        self,
        query: str,
        max_results: int = 50,
        page_token: Optional[str] = None,
        order_by: Optional[str] = 'modifiedTime desc'
    ) -> Dict[str, Any]:
        """
        Search for files in Google Drive.
        
        Args:
            query: Search query (e.g., "name contains 'test'", "mimeType = 'application/pdf'")
            max_results: Maximum number of results (1-100)
            page_token: Token for pagination
        
        Returns:
            Dictionary with 'files' list and 'nextPageToken' if available
        """
        try:
            max_results = min(max(1, max_results), 100)
            
            params = {
                'q': query,
                'pageSize': max_results,
                'fields': (
                    'nextPageToken, '
                    'files('
                    'id, name, mimeType, modifiedTime, size, webViewLink, parents, '
                    'owners(displayName,emailAddress), '
                    'lastModifyingUser(displayName,emailAddress)'
                    ')'
                ),
                'includeItemsFromAllDrives': True,
                'supportsAllDrives': True
            }

            if page_token:
                params['pageToken'] = page_token
            if order_by:
                params['orderBy'] = order_by
            
            response = self.service.files().list(**params).execute()
            
            return {
                'files': response.get('files', []),
                'nextPageToken': response.get('nextPageToken')
            }
        except Exception as e:
            logging.error(f"Error searching files: {str(e)}")
            logging.error(traceback.format_exc())
            return {'files': [], 'nextPageToken': None}
    
    def create_text_file(
        self,
        name: str,
        content: str,
        parent_folder_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new text file.
        
        Args:
            name: File name (must end with .txt, .md, or .json)
            content: File content
            parent_folder_id: Parent folder ID (defaults to root)
        
        Returns:
            Created file information or None if creation fails
        """
        try:
            # Validate extension
            ext = name.split('.')[-1].lower() if '.' in name else ''
            if ext not in TEXT_MIME_TYPES:
                raise ValueError(f"File name must end with .txt, .md, or .json. Got: {name}")
            
            mime_type = TEXT_MIME_TYPES[ext]
            parent_id = parent_folder_id or 'root'
            
            # Create file metadata
            file_metadata = {
                'name': name,
                'mimeType': mime_type,
                'parents': [parent_id]
            }
            
            # Create file with content
            media = MediaIoBaseUpload(
                BytesIO(content.encode('utf-8')),
                mimetype=mime_type,
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, mimeType, webViewLink, modifiedTime',
                supportsAllDrives=True
            ).execute()
            
            return file
        except Exception as e:
            logging.error(f"Error creating text file: {str(e)}")
            logging.error(traceback.format_exc())
            return None
    
    def update_text_file(
        self,
        file_id: str,
        content: str,
        name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing text file.
        
        Args:
            file_id: File ID to update
            content: New file content
            name: Optional new file name
        
        Returns:
            Updated file information or None if update fails
        """
        try:
            # Get current file to check MIME type
            current_file = self.service.files().get(
                fileId=file_id,
                fields='mimeType, name',
                supportsAllDrives=True
            ).execute()
            
            mime_type = current_file.get('mimeType', 'text/plain')
            
            # Validate MIME type is text-based
            if mime_type not in TEXT_MIME_TYPES.values():
                raise ValueError(f"File is not a text file. MIME type: {mime_type}")
            
            # Update metadata if name provided
            update_body = {}
            if name:
                ext = name.split('.')[-1].lower() if '.' in name else ''
                if ext not in TEXT_MIME_TYPES:
                    raise ValueError(f"File name must end with .txt, .md, or .json. Got: {name}")
                update_body['name'] = name
                mime_type = TEXT_MIME_TYPES[ext]
            
            # Update file content
            media = MediaIoBaseUpload(
                BytesIO(content.encode('utf-8')),
                mimetype=mime_type,
                resumable=True
            )
            
            file = self.service.files().update(
                fileId=file_id,
                body=update_body,
                media_body=media,
                fields='id, name, mimeType, webViewLink, modifiedTime',
                supportsAllDrives=True
            ).execute()
            
            return file
        except Exception as e:
            logging.error(f"Error updating text file: {str(e)}")
            logging.error(traceback.format_exc())
            return None
    
    def create_folder(
        self,
        name: str,
        parent_folder_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new folder.
        
        Args:
            name: Folder name
            parent_folder_id: Parent folder ID (defaults to root)
        
        Returns:
            Created folder information or None if creation fails
        """
        try:
            parent_id = parent_folder_id or 'root'
            
            file_metadata = {
                'name': name,
                'mimeType': FOLDER_MIME_TYPE,
                'parents': [parent_id]
            }
            
            folder = self.service.files().create(
                body=file_metadata,
                fields='id, name, mimeType, webViewLink',
                supportsAllDrives=True
            ).execute()
            
            return folder
        except Exception as e:
            logging.error(f"Error creating folder: {str(e)}")
            logging.error(traceback.format_exc())
            return None
    
    def list_folder(
        self,
        folder_id: Optional[str] = None,
        max_results: int = 50,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List contents of a folder.
        
        Args:
            folder_id: Folder ID (defaults to root)
            max_results: Maximum number of results (1-100)
            page_token: Token for pagination
        
        Returns:
            Dictionary with 'files' list and 'nextPageToken' if available
        """
        try:
            folder_id = folder_id or 'root'
            max_results = min(max(1, max_results), 100)
            
            query = f"'{folder_id}' in parents and trashed = false"
            
            params = {
                'q': query,
                'pageSize': max_results,
                'fields': (
                    'nextPageToken, '
                    'files('
                    'id, name, mimeType, modifiedTime, size, webViewLink, parents, '
                    'owners(displayName,emailAddress), '
                    'lastModifyingUser(displayName,emailAddress)'
                    ')'
                ),
                'orderBy': 'name',
                'includeItemsFromAllDrives': True,
                'supportsAllDrives': True
            }
            
            if page_token:
                params['pageToken'] = page_token
            
            response = self.service.files().list(**params).execute()
            
            return {
                'files': response.get('files', []),
                'nextPageToken': response.get('nextPageToken')
            }
        except Exception as e:
            logging.error(f"Error listing folder: {str(e)}")
            logging.error(traceback.format_exc())
            return {'files': [], 'nextPageToken': None}
    
    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get file metadata.
        
        Args:
            file_id: File ID
        
        Returns:
            File information or None if not found
        """
        try:
            file = self.service.files().get(
                fileId=file_id,
                fields=(
                    'id, name, mimeType, modifiedTime, size, webViewLink, parents, '
                    'owners(displayName,emailAddress), '
                    'lastModifyingUser(displayName,emailAddress)'
                ),
                supportsAllDrives=True
            ).execute()
            
            return file
        except Exception as e:
            logging.error(f"Error getting file: {str(e)}")
            logging.error(traceback.format_exc())
            return None

    def resolve_path(
        self,
        parents: Optional[List[str]] = None,
        cache: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        """
        Resolve a folder path using the first parent chain.

        Args:
            parents: Parent folder IDs for a file
            cache: Optional mutable folder metadata cache keyed by folder ID

        Returns:
            POSIX-style folder path rooted at "/"
        """
        if not parents:
            return '/'

        cache = cache if cache is not None else {}
        current = parents[0]
        visited = set()
        components: List[str] = []

        while current and current != 'root' and current not in visited:
            visited.add(current)
            folder = cache.get(current)
            if folder is None:
                folder = self.get_file(current) or {}
                if folder.get('id'):
                    cache[current] = folder
            if not folder:
                break
            name = folder.get('name')
            if name:
                components.append(name)
            folder_parents = folder.get('parents') or []
            current = folder_parents[0] if folder_parents else 'root'

        if not components:
            return '/'
        return '/' + '/'.join(reversed(components))
    
    def get_file_content(self, file_id: str) -> Optional[str]:
        """
        Get file content as text.
        
        Args:
            file_id: File ID
        
        Returns:
            File content as string or None if error
        """
        try:
            # Get file metadata first
            file = self.service.files().get(
                fileId=file_id,
                fields='mimeType',
                supportsAllDrives=True
            ).execute()
            
            mime_type = file.get('mimeType', '')
            
            # Handle Google Workspace files (Docs, Sheets, Slides)
            if mime_type.startswith('application/vnd.google-apps'):
                # Export as text/markdown for docs, CSV for sheets, plain text for slides
                export_mime = 'text/markdown'
                if mime_type == 'application/vnd.google-apps.spreadsheet':
                    export_mime = 'text/csv'
                elif mime_type == 'application/vnd.google-apps.presentation':
                    export_mime = 'text/plain'
                
                response = self.service.files().export_media(
                    fileId=file_id,
                    mimeType=export_mime
                ).execute()
                
                if isinstance(response, bytes):
                    return response.decode('utf-8')
                return str(response)
            else:
                # Regular file download
                response = self.service.files().get_media(
                    fileId=file_id
                ).execute()
                
                if isinstance(response, bytes):
                    return response.decode('utf-8')
                return str(response)
        except Exception as e:
            logging.error(f"Error getting file content: {str(e)}")
            logging.error(traceback.format_exc())
            return None
    
    def delete_file(self, file_id: str) -> bool:
        """
        Move a file or folder to trash.
        
        Args:
            file_id: File or folder ID
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.service.files().update(
                fileId=file_id,
                body={'trashed': True},
                supportsAllDrives=True
            ).execute()
            
            return True
        except Exception as e:
            logging.error(f"Error deleting file: {str(e)}")
            logging.error(traceback.format_exc())
            return False
    
    def rename_file(self, file_id: str, new_name: str) -> Optional[Dict[str, Any]]:
        """
        Rename a file or folder.
        
        Args:
            file_id: File or folder ID
            new_name: New name
        
        Returns:
            Updated file information or None if update fails
        """
        try:
            file = self.service.files().update(
                fileId=file_id,
                body={'name': new_name},
                fields='id, name, modifiedTime',
                supportsAllDrives=True
            ).execute()
            
            return file
        except Exception as e:
            logging.error(f"Error renaming file: {str(e)}")
            logging.error(traceback.format_exc())
            return None
    
    def move_file(
        self,
        file_id: str,
        destination_folder_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Move a file or folder to a different folder.
        
        Args:
            file_id: File or folder ID to move
            destination_folder_id: Destination folder ID (defaults to root)
        
        Returns:
            Updated file information or None if move fails
        """
        try:
            destination_id = destination_folder_id or 'root'
            
            # Get current parents
            file = self.service.files().get(
                fileId=file_id,
                fields='parents',
                supportsAllDrives=True
            ).execute()
            
            previous_parents = ','.join(file.get('parents', []))
            
            # Move file
            file = self.service.files().update(
                fileId=file_id,
                addParents=destination_id,
                removeParents=previous_parents,
                fields='id, name, parents',
                supportsAllDrives=True
            ).execute()
            
            return file
        except Exception as e:
            logging.error(f"Error moving file: {str(e)}")
            logging.error(traceback.format_exc())
            return None
