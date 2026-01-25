"""
Standalone test script for reading PDF info.

Extracts text from a PDF and prints the structured output
(pages, total_pages, extraction_method, warnings, has_text_layer per page).

Usage:
  python covalent_mcp/toolclasses/filesystem/test_read_pdf.py
  python covalent_mcp/toolclasses/filesystem/test_read_pdf.py /path/to/file.pdf
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


DEFAULT_PDF_PATH = "/Users/krishivgubba/Downloads/Krishiv_Gubba_Resume.pdf"


def extract_pdf(path: str) -> tuple[dict | None, str | None]:
    """
    Extract text from a PDF. Same structure as FilesystemClient.read_pdf.
    Returns (result, error_message). error_message is set on failure.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, "pypdf not installed. Run: pip install pypdf"

    p = Path(path).resolve()
    if not p.exists():
        return None, f"File not found: {path}"
    if not p.is_file():
        return None, f"Not a file: {path}"
    if p.suffix.lower() != ".pdf":
        return None, f"Not a PDF (wrong extension): {path}"

    try:
        reader = PdfReader(str(p))
        total = len(reader.pages)
        pages = []
        warnings = []
        for i, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""
            text = raw.strip()
            has_text_layer = bool(text)
            pages.append({
                "page": i,
                "text": raw,
                "has_text_layer": has_text_layer,
            })
        return {
            "pages": pages,
            "total_pages": total,
            "extraction_method": "text",
            "warnings": warnings,
        }, None
    except Exception as e:
        return None, f"Extraction failed: {e}"


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF_PATH
    print(f"PDF path: {path}")
    print()

    result, err = extract_pdf(path)
    if err:
        print(f"ERROR: {err}")
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
