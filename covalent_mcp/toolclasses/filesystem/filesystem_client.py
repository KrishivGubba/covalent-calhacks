"""
Filesystem Client - Local file and directory operations with root-path enforcement.

All operations are scoped to a configurable root directory.
Paths cannot escape the root.
"""
import os
import re
import shutil
from pathlib import Path
from typing import Optional


class FilesystemClient:
    """
    Local filesystem client with root-path enforcement.

    All paths are resolved relative to the root. Operations outside the root
    are rejected.
    """

    def __init__(self, root: str) -> None:
        """
        Initialize the filesystem client.

        Args:
            root: Root directory for all operations. Must be provided.

        Raises:
            ValueError: If root is not a valid directory.
        """
        self._root = Path(root).resolve()
        if not self._root.is_dir():
            raise ValueError(f"Filesystem root is not a directory: {self._root}")

    def _resolve(self, path: str) -> Optional[Path]:
        """
        Resolve a path relative to root. Return None if it escapes root.
        """
        if not path or path == ".":
            return self._root
        p = (self._root / path).resolve()
        try:
            if not p.is_relative_to(self._root):
                return None
        except (ValueError, AttributeError):
            # Python < 3.9: no is_relative_to; use commonpath
            try:
                common = os.path.commonpath([str(p), str(self._root)])
                if os.path.normpath(common) != os.path.normpath(str(self._root)):
                    return None
            except ValueError:
                return None
        return p

    def read_file(self, path: str, encoding: str = "utf-8") -> Optional[str]:
        """
        Read a text file. Returns None if path is invalid, outside root, or not a file.
        """
        p = self._resolve(path)
        if not p or not p.is_file():
            return None
        try:
            return p.read_text(encoding=encoding)
        except (OSError, UnicodeDecodeError):
            return None

    def write_file(
        self, path: str, content: str, encoding: str = "utf-8", create_dirs: bool = True
    ) -> bool:
        """
        Write content to a text file. Creates parent directories if create_dirs is True.
        """
        p = self._resolve(path)
        if not p:
            return False
        try:
            if create_dirs:
                p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding=encoding)
            return True
        except OSError:
            return False

    def list_directory(self, path: str = ".") -> Optional[list[dict]]:
        """
        List directory contents. Returns list of {"name", "path", "is_dir"} or None.
        """
        p = self._resolve(path)
        if not p or not p.is_dir():
            return None
        try:
            entries = []
            for e in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                rel = e.relative_to(self._root) if e != self._root else Path(".")
                entries.append({
                    "name": e.name,
                    "path": str(rel).replace("\\", "/"),
                    "is_dir": e.is_dir(),
                })
            return entries
        except OSError:
            return None

    def create_directory(self, path: str, parents: bool = True) -> bool:
        """
        Create a directory. Creates parent directories if parents is True.
        """
        p = self._resolve(path)
        if not p:
            return False
        try:
            p.mkdir(parents=parents, exist_ok=True)
            return True
        except OSError:
            return False

    def delete_path(self, path: str, recursive: bool = False) -> tuple[bool, Optional[str]]:
        """
        Delete a file or directory.
        - File: always deleted.
        - Directory: deleted only if empty, unless recursive is True.

        Returns (success, error_message). error_message is set on failure.
        """
        p = self._resolve(path)
        if not p:
            return False, "Path outside allowed root or invalid"
        if not p.exists():
            return False, "Path does not exist"
        try:
            if p.is_file():
                p.unlink()
                return True, None
            if p.is_dir():
                if recursive:
                    shutil.rmtree(p)
                    return True, None
                p.rmdir()
                return True, None
        except OSError as e:
            return False, str(e)
        return False, "Unknown error"

    def file_exists(self, path: str) -> bool:
        """Check if a path exists (file or directory)."""
        p = self._resolve(path)
        return p is not None and p.exists()

    def move_path(self, src: str, dst: str) -> tuple[bool, Optional[str]]:
        """
        Move or rename a file or directory. Returns (success, error_message).
        """
        sp = self._resolve(src)
        dp = self._resolve(dst)
        if not sp or not dp:
            return False, "Path outside allowed root or invalid"
        if not sp.exists():
            return False, "Source does not exist"
        try:
            shutil.move(str(sp), str(dp))
            return True, None
        except OSError as e:
            return False, str(e)

    def copy_path(self, src: str, dst: str) -> tuple[bool, Optional[str]]:
        """
        Copy a file or directory. Returns (success, error_message).
        """
        sp = self._resolve(src)
        dp = self._resolve(dst)
        if not sp or not dp:
            return False, "Path outside allowed root or invalid"
        if not sp.exists():
            return False, "Source does not exist"
        try:
            if sp.is_file():
                shutil.copy2(str(sp), str(dp))
            else:
                shutil.copytree(str(sp), str(dp))
            return True, None
        except OSError as e:
            return False, str(e)

    def search_directory(
        self,
        path: str,
        pattern: str,
        max_matches: int = 25,
        recursive: bool = True,
        use_regex: bool = False,
        encoding: str = "utf-8",
    ) -> Optional[tuple[list[dict], bool]]:
        """
        Search directory for pattern in file contents (grep-style).
        Returns (matches, truncated). matches: list of {"path", "line_number", "line"} up to max_matches.
        truncated is True if we stopped due to max_matches. None if path invalid or invalid regex.
        Skips binary files. Path is relative to root.
        """
        p = self._resolve(path)
        if not p or not p.is_dir():
            return None
        matches: list[dict] = []
        try:
            regex = re.compile(pattern) if use_regex else None
        except re.error:
            return None
        it = p.rglob("*") if recursive else p.iterdir()
        truncated = False
        for f in sorted(it, key=lambda x: str(x)):
            if not f.is_file():
                continue
            if len(matches) >= max_matches:
                truncated = True
                break
            try:
                text = f.read_text(encoding=encoding)
            except (OSError, UnicodeDecodeError):
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                if len(matches) >= max_matches:
                    truncated = True
                    break
                hit = (use_regex and regex.search(line)) or (not use_regex and pattern in line)
                if hit:
                    rel = f.relative_to(self._root)
                    matches.append({
                        "path": str(rel).replace("\\", "/"),
                        "line_number": i,
                        "line": line,
                    })
            if truncated:
                break
        return (matches, truncated)

    def read_pdf(self, path: str) -> Optional[dict]:
        """
        Extract text from a PDF. Returns structured dict:
        {"pages": [{"page": n, "text": "...", "has_text_layer": bool}], "total_pages": n,
         "extraction_method": "text", "warnings": []}
        or None if path invalid / not a PDF / extraction fails.
        """
        p = self._resolve(path)
        if not p or not p.is_file() or p.suffix.lower() != ".pdf":
            return None
        try:
            from pypdf import PdfReader
        except ImportError:
            return None
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
            }
        except Exception:
            return None

    @property
    def root(self) -> Path:
        """The configured root directory."""
        return self._root
