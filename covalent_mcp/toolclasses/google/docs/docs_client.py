"""
Google Docs API Client - Wrapper for Docs and related Drive operations.

Provides methods for reading, writing, and formatting Google Documents,
as well as managing tabs, tables, and comments.
"""
from typing import Optional, List, Dict, Any, Tuple
import logging

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from google.oauth2.credentials import Credentials
except ImportError:
    raise ImportError(
        "Google API client not installed. Install with: pip install google-api-python-client"
    )

from covalent_mcp.toolclasses.google.gauth import get_credentials_from_db

DOCS_MIME_TYPE = "application/vnd.google-apps.document"


class DocsService:
    """
    Google Docs service wrapper.

    Wraps both the Docs v1 API (document content) and Drive v3 API
    (document creation, comments).
    """

    def __init__(self, credentials: Optional[Credentials] = None):
        if credentials is None:
            credentials = get_credentials_from_db()
        self.credentials = credentials
        self.docs_service = build("docs", "v1", credentials=credentials)
        self.drive_service = build("drive", "v3", credentials=credentials)

    # =========================================================================
    # Private helpers
    # =========================================================================

    def _http_error(self, e: HttpError) -> RuntimeError:
        try:
            import json as _json
            body = _json.loads(e.content.decode("utf-8", errors="replace"))
            message = body.get("error", {}).get("message") or str(e)
        except Exception:
            message = str(e)
        status = e.resp.status
        if status == 403:
            message += " (If this is a scope error, disconnect and reconnect Google in Dashboard → Integrations to grant the 'documents' permission.)"
        return RuntimeError(f"Google API error {status}: {message}")

    def _extract_text(self, content_source: dict) -> str:
        """Extract plain text from a document content source (body or tab body)."""
        text = ""
        for element in content_source.get("body", {}).get("content", []):
            if "paragraph" in element:
                for pe in element["paragraph"].get("elements", []):
                    text += pe.get("textRun", {}).get("content", "")
            elif "table" in element:
                for row in element["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        for ce in cell.get("content", []):
                            for pe in ce.get("paragraph", {}).get("elements", []):
                                text += pe.get("textRun", {}).get("content", "")
        return text

    def _find_text_range(
        self,
        content_source: dict,
        text_to_find: str,
        match_instance: int = 1,
    ) -> Optional[Tuple[int, int]]:
        """
        Find the Nth occurrence of text_to_find in a content source.

        Returns (startIndex, endIndex) or None. Indices are the 1-based
        character indices used by the Google Docs API.
        """
        # Collect all (startIndex, endIndex, content) tuples from text runs
        runs: List[Tuple[int, int, str]] = []
        for element in content_source.get("body", {}).get("content", []):
            if "paragraph" in element:
                for pe in element["paragraph"].get("elements", []):
                    if "textRun" in pe and "startIndex" in pe:
                        runs.append(
                            (pe["startIndex"], pe["endIndex"], pe["textRun"].get("content", ""))
                        )
            elif "table" in element:
                for row in element["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        for ce in cell.get("content", []):
                            for pe in ce.get("paragraph", {}).get("elements", []):
                                if "textRun" in pe and "startIndex" in pe:
                                    runs.append(
                                        (
                                            pe["startIndex"],
                                            pe["endIndex"],
                                            pe["textRun"].get("content", ""),
                                        )
                                    )

        # Concatenate into one big string keeping track of index offsets
        combined = ""
        offset_map: List[int] = []  # combined_pos -> api_index
        for start_idx, _end_idx, content in runs:
            for i, ch in enumerate(content):
                combined += ch
                offset_map.append(start_idx + i)

        # Find Nth occurrence
        search_start = 0
        for _ in range(match_instance):
            pos = combined.find(text_to_find, search_start)
            if pos == -1:
                return None
            search_start = pos + 1

        # Map back to API indices
        api_start = offset_map[pos]
        api_end = offset_map[pos + len(text_to_find) - 1] + 1
        return api_start, api_end

    def _get_content_source(self, doc: dict, tab_id: Optional[str]) -> dict:
        """
        Return the content source dict for the given tab_id, or the whole doc
        for legacy single-tab documents.
        """
        if not tab_id:
            return doc
        for tab in doc.get("tabs", []):
            if tab.get("tabProperties", {}).get("tabId") == tab_id:
                document_tab = tab.get("documentTab")
                if document_tab is None:
                    raise ValueError(f"Tab '{tab_id}' does not have document content.")
                return document_tab
        raise ValueError(f"Tab '{tab_id}' not found in document.")

    def _hex_to_rgb(self, hex_color: str) -> Dict[str, float]:
        """Convert '#RRGGBB' or '#RGB' to Google Docs rgbColor dict."""
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = h[0] * 2 + h[1] * 2 + h[2] * 2
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
        return {"red": r, "green": g, "blue": b}

    def _build_text_style_request(
        self,
        start: int,
        end: int,
        style: dict,
        tab_id: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Build an updateTextStyle batchUpdate request.

        style keys (all optional):
          bold, italic, underline, strikethrough (bool)
          fontSize (number, in points)
          fontFamily (str)
          foregroundColor, backgroundColor (hex string '#RRGGBB')
        """
        text_style: dict = {}
        fields: List[str] = []

        for flag in ("bold", "italic", "underline", "strikethrough"):
            if flag in style:
                text_style[flag] = bool(style[flag])
                fields.append(flag)

        if "fontSize" in style:
            text_style["fontSize"] = {"magnitude": float(style["fontSize"]), "unit": "PT"}
            fields.append("fontSize")

        if "fontFamily" in style:
            text_style["weightedFontFamily"] = {"fontFamily": style["fontFamily"]}
            fields.append("weightedFontFamily")

        if "foregroundColor" in style:
            text_style["foregroundColor"] = {
                "color": {"rgbColor": self._hex_to_rgb(style["foregroundColor"])}
            }
            fields.append("foregroundColor")

        if "backgroundColor" in style:
            text_style["backgroundColor"] = {
                "color": {"rgbColor": self._hex_to_rgb(style["backgroundColor"])}
            }
            fields.append("backgroundColor")

        if not fields:
            return None

        range_obj: dict = {"startIndex": start, "endIndex": end}
        if tab_id:
            range_obj["tabId"] = tab_id

        return {
            "updateTextStyle": {
                "range": range_obj,
                "textStyle": text_style,
                "fields": ",".join(fields),
            }
        }

    def _build_paragraph_style_request(
        self,
        start: int,
        end: int,
        style: dict,
        tab_id: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Build an updateParagraphStyle batchUpdate request.

        style keys (all optional):
          alignment: 'START' | 'END' | 'CENTER' | 'JUSTIFIED'
          namedStyleType: 'NORMAL_TEXT' | 'TITLE' | 'HEADING_1' ... 'HEADING_6'
          spaceAbove, spaceBelow (number, in points)
          lineSpacing (number, 100 = single spacing)
          indentFirstLine, indentStart (number, in points)
        """
        para_style: dict = {}
        fields: List[str] = []

        if "alignment" in style:
            para_style["alignment"] = style["alignment"]
            fields.append("alignment")

        if "namedStyleType" in style:
            para_style["namedStyleType"] = style["namedStyleType"]
            fields.append("namedStyleType")

        if "spaceAbove" in style:
            para_style["spaceAbove"] = {"magnitude": float(style["spaceAbove"]), "unit": "PT"}
            fields.append("spaceAbove")

        if "spaceBelow" in style:
            para_style["spaceBelow"] = {"magnitude": float(style["spaceBelow"]), "unit": "PT"}
            fields.append("spaceBelow")

        if "lineSpacing" in style:
            para_style["lineSpacing"] = float(style["lineSpacing"])
            fields.append("lineSpacing")

        if "indentFirstLine" in style:
            para_style["indentFirstLine"] = {
                "magnitude": float(style["indentFirstLine"]),
                "unit": "PT",
            }
            fields.append("indentFirstLine")

        if "indentStart" in style:
            para_style["indentStart"] = {
                "magnitude": float(style["indentStart"]),
                "unit": "PT",
            }
            fields.append("indentStart")

        if not fields:
            return None

        range_obj: dict = {"startIndex": start, "endIndex": end}
        if tab_id:
            range_obj["tabId"] = tab_id

        return {
            "updateParagraphStyle": {
                "range": range_obj,
                "paragraphStyle": para_style,
                "fields": ",".join(fields),
            }
        }

    def _batch_update(self, document_id: str, requests: list) -> dict:
        try:
            return (
                self.docs_service.documents()
                .batchUpdate(documentId=document_id, body={"requests": requests})
                .execute()
            )
        except HttpError as e:
            raise self._http_error(e)

    # =========================================================================
    # Public API
    # =========================================================================

    def get_document(
        self,
        document_id: str,
        fields: str = "*",
        include_tabs: bool = False,
    ) -> dict:
        """Fetch a Google Document."""
        try:
            return (
                self.docs_service.documents()
                .get(
                    documentId=document_id,
                    includeTabsContent=include_tabs,
                    fields=fields,
                )
                .execute()
            )
        except HttpError as e:
            raise self._http_error(e)

    def create_document(self, title: str) -> dict:
        """Create a new blank Google Document via the Drive API."""
        try:
            file_meta = {
                "name": title,
                "mimeType": DOCS_MIME_TYPE,
            }
            return (
                self.drive_service.files()
                .create(
                    body=file_meta,
                    fields="id,name,webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except HttpError as e:
            raise self._http_error(e)

    # -------------------------------------------------------------------------
    # Read
    # -------------------------------------------------------------------------

    def read_document(
        self,
        document_id: str,
        format: str = "text",
        tab_id: Optional[str] = None,
        max_length: Optional[int] = None,
    ) -> str:
        """
        Read a Google Document as plain text or JSON.

        format='text'  — extract all text runs
        format='json'  — return raw API structure as JSON string
        """
        import json

        include_tabs = bool(tab_id)
        if format == "json":
            doc = self.get_document(document_id, fields="*", include_tabs=include_tabs)
            content_source = self._get_content_source(doc, tab_id)
            result = json.dumps(content_source, indent=2)
            if max_length and len(result) > max_length:
                return result[:max_length] + f"\n... [truncated: {len(result)} total chars]"
            return result

        # text (or markdown fallback — return plain text)
        doc = self.get_document(document_id, fields="*", include_tabs=include_tabs)
        content_source = self._get_content_source(doc, tab_id)
        text = self._extract_text(content_source)

        if not text.strip():
            return "Document found, but appears empty."

        if max_length and len(text) > max_length:
            return (
                f"Content (truncated to {max_length} chars of {len(text)} total):\n---\n"
                + text[:max_length]
                + f"\n\n... [Document continues. Remove max_length to get full content.]"
            )

        return f"Content ({len(text)} characters):\n---\n{text}"

    # -------------------------------------------------------------------------
    # Text mutations
    # -------------------------------------------------------------------------

    def append_text(
        self,
        document_id: str,
        text: str,
        add_newline: bool = True,
        tab_id: Optional[str] = None,
    ) -> dict:
        """Append text to the end of a document."""
        include_tabs = bool(tab_id)
        doc = self.get_document(
            document_id,
            fields="body(content(endIndex))" if not tab_id else "*",
            include_tabs=include_tabs,
        )
        content_source = self._get_content_source(doc, tab_id)
        content = content_source.get("body", {}).get("content", [])

        if not content:
            insert_index = 1
        else:
            # endIndex of the last element minus 1 to land before trailing newline
            insert_index = max(1, content[-1].get("endIndex", 2) - 1)

        final_text = ("\n" + text) if add_newline else text

        location: dict = {"index": insert_index}
        if tab_id:
            location["tabId"] = tab_id

        return self._batch_update(document_id, [{"insertText": {"location": location, "text": final_text}}])

    def insert_text(
        self,
        document_id: str,
        text: str,
        index: int,
        tab_id: Optional[str] = None,
    ) -> dict:
        """Insert text at a 1-based character index."""
        location: dict = {"index": max(1, index)}
        if tab_id:
            location["tabId"] = tab_id
        return self._batch_update(document_id, [{"insertText": {"location": location, "text": text}}])

    def delete_range(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        tab_id: Optional[str] = None,
    ) -> dict:
        """Delete a [startIndex, endIndex) character range."""
        if end_index <= start_index:
            raise ValueError("end_index must be greater than start_index")
        range_obj: dict = {"startIndex": start_index, "endIndex": end_index}
        if tab_id:
            range_obj["tabId"] = tab_id
        return self._batch_update(document_id, [{"deleteContentRange": {"range": range_obj}}])

    def find_and_replace(
        self,
        document_id: str,
        find_text: str,
        replace_text: str,
        match_case: bool = False,
        tab_id: Optional[str] = None,
    ) -> dict:
        """Replace all occurrences of find_text with replace_text."""
        replace_request: dict = {
            "containsText": {"text": find_text, "matchCase": match_case},
            "replaceText": replace_text,
        }
        if tab_id:
            replace_request["tabsCriteria"] = {"tabIds": [tab_id]}
        return self._batch_update(document_id, [{"replaceAllText": replace_request}])

    def modify_text(
        self,
        document_id: str,
        start_index: int,
        end_index: Optional[int] = None,
        text: Optional[str] = None,
        style: Optional[dict] = None,
        tab_id: Optional[str] = None,
    ) -> dict:
        """
        Combined text replacement and/or formatting in one batch.

        - If end_index given and text given: delete range then insert text.
        - If only text: insert at start_index.
        - If style given: apply text style to the resulting range.
        """
        if text is None and style is None:
            raise ValueError("At least one of text or style must be provided.")

        requests = []

        if end_index is not None and text is not None:
            # Replace: delete then insert
            range_obj: dict = {"startIndex": start_index, "endIndex": end_index}
            if tab_id:
                range_obj["tabId"] = tab_id
            requests.append({"deleteContentRange": {"range": range_obj}})

        if text is not None:
            location: dict = {"index": start_index}
            if tab_id:
                location["tabId"] = tab_id
            requests.append({"insertText": {"location": location, "text": text}})

        if style is not None:
            style_end = (
                start_index + len(text)
                if text is not None
                else (end_index if end_index is not None else start_index)
            )
            if style_end > start_index:
                req = self._build_text_style_request(start_index, style_end, style, tab_id)
                if req:
                    requests.append(req)

        if not requests:
            return {"success": True, "message": "No operations to perform."}

        return self._batch_update(document_id, requests)

    # -------------------------------------------------------------------------
    # Formatting
    # -------------------------------------------------------------------------

    def apply_text_style(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        style: dict,
        tab_id: Optional[str] = None,
    ) -> dict:
        """Apply character-level formatting to a range."""
        req = self._build_text_style_request(start_index, end_index, style, tab_id)
        if not req:
            raise ValueError("No valid style fields provided.")
        return self._batch_update(document_id, [req])

    def apply_paragraph_style(
        self,
        document_id: str,
        start_index: int,
        end_index: int,
        style: dict,
        tab_id: Optional[str] = None,
    ) -> dict:
        """Apply paragraph-level formatting to a range."""
        req = self._build_paragraph_style_request(start_index, end_index, style, tab_id)
        if not req:
            raise ValueError("No valid style fields provided.")
        return self._batch_update(document_id, [req])

    # -------------------------------------------------------------------------
    # Structure
    # -------------------------------------------------------------------------

    def insert_table(
        self,
        document_id: str,
        index: int,
        rows: int,
        columns: int,
        tab_id: Optional[str] = None,
    ) -> dict:
        """Insert an empty table at the given index."""
        location: dict = {"index": index}
        if tab_id:
            location["tabId"] = tab_id
        return self._batch_update(
            document_id,
            [{"insertTable": {"location": location, "rows": rows, "columns": columns}}],
        )

    def insert_table_with_data(
        self,
        document_id: str,
        index: int,
        data: List[List[str]],
        has_header_row: bool = False,
        tab_id: Optional[str] = None,
    ) -> dict:
        """
        Insert a table pre-populated with data.

        Uses the cell index formula from the TypeScript reference:
          cell_base = T + 4 + r*(1 + 2*C) + 2*c
        Plus a cumulative_offset for text already inserted into prior cells.
        """
        if not data or not data[0]:
            raise ValueError("data must be a non-empty 2D list")

        num_cols = max(len(row) for row in data)
        num_rows = len(data)

        # Pad rows to uniform width
        padded = [row + [""] * (num_cols - len(row)) for row in data]

        # First insert the empty table
        location: dict = {"index": index}
        if tab_id:
            location["tabId"] = tab_id

        requests = [{"insertTable": {"location": location, "rows": num_rows, "columns": num_cols}}]

        # Then fill cells. The table is inserted AT `index`, pushing subsequent
        # content forward. The first cell content starts at:
        #   T + 4 + 0*(1 + 2*C) + 2*0  =  T + 4
        # where T = index (the table's own start index in the doc after insertion).
        # But since insertTable pushes the index of the insertion point forward by
        # the table's structural tokens, each subsequent insertText must account for
        # text already inserted (cumulative_offset).
        cumulative_offset = 0

        for r in range(num_rows):
            for c in range(num_cols):
                cell_text = padded[r][c]
                if not cell_text:
                    continue
                cell_base = index + 4 + r * (1 + 2 * num_cols) + 2 * c
                insert_idx = cell_base + cumulative_offset

                cell_location: dict = {"index": insert_idx}
                if tab_id:
                    cell_location["tabId"] = tab_id
                requests.append(
                    {"insertText": {"location": cell_location, "text": cell_text}}
                )
                cumulative_offset += len(cell_text)

        result = self._batch_update(document_id, requests)

        # Bold first row if it's a header
        if has_header_row and padded[0]:
            # Header cells: row 0, all columns
            # After inserting, the first row starts at index + 4 + cumulative header text
            # We use find_and_replace approach is unreliable; instead style by known range.
            # Header row style requests need a second batch after knowing final indices.
            # Use a separate read + style pass.
            try:
                doc = self.get_document(document_id, fields="*", include_tabs=bool(tab_id))
                cs = self._get_content_source(doc, tab_id)
                for element in cs.get("body", {}).get("content", []):
                    if "table" in element and element.get("startIndex") == index:
                        table = element["table"]
                        if table.get("tableRows"):
                            header_row = table["tableRows"][0]
                            style_reqs = []
                            for cell in header_row.get("tableCells", []):
                                for cell_el in cell.get("content", []):
                                    for pe in cell_el.get("paragraph", {}).get("elements", []):
                                        if "textRun" in pe and pe.get("startIndex") is not None:
                                            r_obj: dict = {
                                                "startIndex": pe["startIndex"],
                                                "endIndex": pe["endIndex"],
                                            }
                                            if tab_id:
                                                r_obj["tabId"] = tab_id
                                            style_reqs.append(
                                                {
                                                    "updateTextStyle": {
                                                        "range": r_obj,
                                                        "textStyle": {"bold": True},
                                                        "fields": "bold",
                                                    }
                                                }
                                            )
                            if style_reqs:
                                self._batch_update(document_id, style_reqs)
                        break
            except Exception:
                pass  # header bold is best-effort

        return result

    def insert_page_break(
        self,
        document_id: str,
        index: int,
        tab_id: Optional[str] = None,
    ) -> dict:
        """Insert a page break at the given index."""
        location: dict = {"index": index}
        if tab_id:
            location["tabId"] = tab_id
        return self._batch_update(
            document_id,
            [{"insertPageBreak": {"location": location}}],
        )

    # -------------------------------------------------------------------------
    # Tabs
    # -------------------------------------------------------------------------

    def list_tabs(self, document_id: str) -> dict:
        """List all tabs in a document with their IDs and hierarchy."""
        doc = self.get_document(
            document_id,
            fields="title,tabs(tabProperties,childTabs)",
            include_tabs=True,
        )
        title = doc.get("title", "Untitled")

        def flatten_tabs(tabs: list, parent_id: Optional[str] = None) -> list:
            result = []
            for tab in tabs or []:
                props = tab.get("tabProperties", {})
                result.append(
                    {
                        "tabId": props.get("tabId"),
                        "title": props.get("title", "Untitled"),
                        "index": props.get("index"),
                        "parentTabId": parent_id,
                    }
                )
                result.extend(flatten_tabs(tab.get("childTabs", []), props.get("tabId")))
            return result

        return {"title": title, "tabs": flatten_tabs(doc.get("tabs", []))}

    def add_tab(
        self,
        document_id: str,
        title: Optional[str] = None,
        parent_tab_id: Optional[str] = None,
        index: Optional[int] = None,
    ) -> dict:
        """Create a new tab in the document."""
        tab_properties: dict = {}
        if title:
            tab_properties["title"] = title
        if index is not None:
            tab_properties["index"] = index

        create_tab: dict = {"tabProperties": tab_properties}
        if parent_tab_id:
            create_tab["insertTabProperties"] = {"parentTabId": parent_tab_id}

        result = self._batch_update(document_id, [{"createTab": create_tab}])
        return result

    def rename_tab(self, document_id: str, tab_id: str, new_title: str) -> dict:
        """Rename an existing tab."""
        return self._batch_update(
            document_id,
            [
                {
                    "updateDocumentTab": {
                        "documentTab": {
                            "tabProperties": {"tabId": tab_id, "title": new_title}
                        },
                        "fields": "tabProperties.title",
                    }
                }
            ],
        )

    # -------------------------------------------------------------------------
    # Comments (Drive API v3)
    # -------------------------------------------------------------------------

    def list_comments(self, document_id: str) -> dict:
        """List all comments on a document."""
        try:
            response = (
                self.drive_service.comments()
                .list(
                    fileId=document_id,
                    fields="comments(id,author,content,quotedFileContent,resolved,createdTime,modifiedTime,replies),nextPageToken",
                    pageSize=100,
                )
                .execute()
            )
            comments = response.get("comments", [])
            return {
                "count": len(comments),
                "comments": [
                    {
                        "id": c.get("id"),
                        "author": c.get("author", {}).get("displayName"),
                        "content": c.get("content"),
                        "quotedText": c.get("quotedFileContent", {}).get("value"),
                        "resolved": c.get("resolved", False),
                        "createdTime": c.get("createdTime"),
                        "modifiedTime": c.get("modifiedTime"),
                        "replyCount": len(c.get("replies", [])),
                    }
                    for c in comments
                ],
            }
        except HttpError as e:
            raise self._http_error(e)

    def get_comment(self, document_id: str, comment_id: str) -> dict:
        """Get a specific comment with its reply thread."""
        try:
            c = (
                self.drive_service.comments()
                .get(
                    fileId=document_id,
                    commentId=comment_id,
                    fields="*",
                    includeDeleted=False,
                )
                .execute()
            )
            replies = [
                {
                    "id": r.get("id"),
                    "author": r.get("author", {}).get("displayName"),
                    "content": r.get("content"),
                    "createdTime": r.get("createdTime"),
                }
                for r in c.get("replies", [])
            ]
            return {
                "id": c.get("id"),
                "author": c.get("author", {}).get("displayName"),
                "content": c.get("content"),
                "quotedText": c.get("quotedFileContent", {}).get("value"),
                "resolved": c.get("resolved", False),
                "createdTime": c.get("createdTime"),
                "replies": replies,
            }
        except HttpError as e:
            raise self._http_error(e)

    def add_comment(
        self,
        document_id: str,
        content: str,
        start_index: int,
        end_index: int,
    ) -> dict:
        """
        Add a comment anchored to a text range.

        Reads the document to extract quoted text from the range, then creates
        the comment via the Drive API.
        """
        # Extract quoted text from range
        try:
            doc = self.get_document(
                document_id,
                fields="body(content(startIndex,endIndex,paragraph(elements(startIndex,endIndex,textRun(content)))))",
            )
            quoted_text = ""
            for element in doc.get("body", {}).get("content", []):
                if "paragraph" in element:
                    for pe in element["paragraph"].get("elements", []):
                        if "textRun" in pe and "startIndex" in pe:
                            pe_start = pe["startIndex"]
                            pe_end = pe["endIndex"]
                            text = pe["textRun"].get("content", "")
                            # Overlap with [start_index, end_index)
                            overlap_start = max(pe_start, start_index)
                            overlap_end = min(pe_end, end_index)
                            if overlap_start < overlap_end:
                                local_start = overlap_start - pe_start
                                local_end = overlap_end - pe_start
                                quoted_text += text[local_start:local_end]
        except Exception:
            quoted_text = ""

        # Drive API uses 0-based offset/length for anchor
        offset = start_index - 1
        length = end_index - start_index

        anchor = {
            "r": "head",
            "a": [
                {
                    "pos": {"tbl": {"off": offset}},
                    "len": length,
                }
            ],
        }

        try:
            import json

            result = (
                self.drive_service.comments()
                .create(
                    fileId=document_id,
                    fields="id,content,author,createdTime",
                    body={
                        "content": content,
                        "quotedFileContent": {
                            "mimeType": "text/plain",
                            "value": quoted_text,
                        },
                        "anchor": json.dumps(anchor),
                    },
                )
                .execute()
            )
            return {
                "id": result.get("id"),
                "content": result.get("content"),
                "author": result.get("author", {}).get("displayName"),
                "createdTime": result.get("createdTime"),
            }
        except HttpError as e:
            raise self._http_error(e)

    def reply_to_comment(
        self, document_id: str, comment_id: str, content: str
    ) -> dict:
        """Add a reply to an existing comment thread."""
        try:
            result = (
                self.drive_service.replies()
                .create(
                    fileId=document_id,
                    commentId=comment_id,
                    fields="id,content,author,createdTime",
                    body={"content": content},
                )
                .execute()
            )
            return {
                "id": result.get("id"),
                "content": result.get("content"),
                "author": result.get("author", {}).get("displayName"),
                "createdTime": result.get("createdTime"),
            }
        except HttpError as e:
            raise self._http_error(e)

    def resolve_comment(self, document_id: str, comment_id: str) -> dict:
        """
        Mark a comment as resolved.

        Note: Due to a Google Drive API limitation, the resolved status may not
        visually persist in the Google Docs UI. It can be resolved manually
        via the Google Docs interface if needed.
        """
        try:
            result = (
                self.drive_service.comments()
                .update(
                    fileId=document_id,
                    commentId=comment_id,
                    fields="id,resolved",
                    body={"resolved": True},
                )
                .execute()
            )
            return {"id": result.get("id"), "resolved": result.get("resolved", False)}
        except HttpError as e:
            raise self._http_error(e)

    def delete_comment(self, document_id: str, comment_id: str) -> None:
        """Permanently delete a comment and all its replies."""
        try:
            self.drive_service.comments().delete(
                fileId=document_id, commentId=comment_id
            ).execute()
        except HttpError as e:
            raise self._http_error(e)
