"""
Test script for Filesystem MCP tools.

Uses project_root/testing as the filesystem root. Creates it if missing.
Run from project root:
  python covalent_mcp/toolclasses/filesystem/test_script.py
  python -m covalent_mcp.toolclasses.filesystem.test_script  # requires deps

Loads FilesystemClient directly (no toolclasses deps like requests) so you can
run without installing full project deps.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Resolve project root and testing dir
# test_script.py -> filesystem/ -> toolclasses/ -> covalent_mcp/ -> project root
_covalent_mcp = Path(__file__).resolve().parents[2]
_project_root = _covalent_mcp.parent
TESTING_DIR = _project_root / "testing"


# Load FilesystemClient directly to avoid pulling in toolclasses (github, etc.)
_client_path = Path(__file__).resolve().parent / "filesystem_client.py"
_spec = importlib.util.spec_from_file_location("filesystem_client", _client_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
FilesystemClient = _mod.FilesystemClient


def _section(title: str) -> None:
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def main() -> None:
    # Ensure testing dir exists; use it as fs root
    TESTING_DIR.mkdir(exist_ok=True)
    client = FilesystemClient(root=str(TESTING_DIR))

    _section("Root")
    print(f"Filesystem root: {client.root}")
    print()

    # --- create_directory ---
    _section("create_directory")
    ok = client.create_directory("subdir", parents=True)
    print(f"create_directory('subdir'): {ok}")
    ok2 = client.create_directory("subdir/nested", parents=True)
    print(f"create_directory('subdir/nested'): {ok2}")
    print()

    # --- write_file ---
    _section("write_file")
    content = "hello world\nline two\nhello again\nMCPToolModule mention"
    ok = client.write_file("subdir/foo.txt", content, create_dirs=True)
    print(f"write_file('subdir/foo.txt'): {ok}")
    ok2 = client.write_file("subdir/nested/other.txt", "nested file\nhello", create_dirs=True)
    print(f"write_file('subdir/nested/other.txt'): {ok2}")
    print()

    # --- read_file ---
    _section("read_file")
    out = client.read_file("subdir/foo.txt")
    print(f"read_file('subdir/foo.txt'): {bool(out)}")
    if out:
        print(f"  First 50 chars: {repr(out[:50])}...")
    print()

    # --- list_directory ---
    _section("list_directory")
    entries = client.list_directory(".")
    print(f"list_directory('.'): {len(entries) if entries else 0} entries")
    if entries:
        for e in entries[:8]:
            icon = "📁" if e["is_dir"] else "📄"
            print(f"  {icon} {e['path']}")
    entries2 = client.list_directory("subdir")
    print(f"list_directory('subdir'): {len(entries2) if entries2 else 0} entries")
    if entries2:
        for e in entries2[:5]:
            icon = "📁" if e["is_dir"] else "📄"
            print(f"  {icon} {e['path']}")
    print()

    # --- grep ---
    _section("grep")
    result = client.search_directory(".", "hello", max_matches=10, recursive=True)
    if result is None:
        print("grep('.', 'hello'): FAILED (invalid path/regex)")
    else:
        matches, truncated = result
        print(f"grep('.', 'hello'): {len(matches)} matches, truncated={truncated}")
        for m in matches[:5]:
            print(f"  {m['path']}:{m['line_number']}  {m['line'][:60]!r}")
    print()

    # --- read_pdf ---
    _section("read_pdf")
    try:
        from pypdf import PdfWriter
    except ImportError:
        print("read_pdf: SKIP (pypdf not installed)")
    else:
        pdf_path = Path(client.root) / "sample.pdf"
        w = PdfWriter()
        w.add_blank_page(200, 200)
        with open(pdf_path, "wb") as f:
            w.write(f)
        rel = "sample.pdf"
        r = client.read_pdf(rel)
        if r is None:
            print(f"read_pdf('{rel}'): FAILED")
        else:
            print(f"read_pdf('{rel}'): {r['total_pages']} page(s)")
            print(f"  extraction_method: {r['extraction_method']}")
            for p in r["pages"][:2]:
                print(f"  page {p['page']}: has_text_layer={p['has_text_layer']}, text_len={len(p['text'])}")
        # pdf_path.unlink(missing_ok=True)  # commented out so you can inspect sample.pdf
    print()

    # --- file_exists ---
    _section("file_exists")
    print(f"file_exists('subdir/foo.txt'): {client.file_exists('subdir/foo.txt')}")
    print(f"file_exists('subdir/missing.txt'): {client.file_exists('subdir/missing.txt')}")
    print()

    # --- copy_path ---
    _section("copy_path")
    ok, err = client.copy_path("subdir/foo.txt", "subdir/bar.txt")
    print(f"copy_path('subdir/foo.txt' -> 'subdir/bar.txt'): {ok}" + (f" ({err})" if err else ""))
    out = client.read_file("subdir/bar.txt")
    print(f"  Verify copy: {bool(out)} (content match: {out == content})")
    print()

    # --- move_path ---
    _section("move_path")
    ok, err = client.move_path("subdir/bar.txt", "moved.txt")
    print(f"move_path('subdir/bar.txt' -> 'moved.txt'): {ok}" + (f" ({err})" if err else ""))
    print(f"  file_exists('subdir/bar.txt'): {client.file_exists('subdir/bar.txt')}")
    print(f"  file_exists('moved.txt'): {client.file_exists('moved.txt')}")
    print()

    # --- delete_path (commented out so you can inspect created files) ---
    # _section("delete_path")
    # ok, err = client.delete_path("moved.txt")
    # print(f"delete_path('moved.txt'): {ok}" + (f" ({err})" if err else ""))
    # ok2, err2 = client.delete_path("subdir/nested/other.txt")
    # print(f"delete_path('subdir/nested/other.txt'): {ok2}" + (f" ({err2})" if err2 else ""))
    # ok3, err3 = client.delete_path("subdir/nested")
    # print(f"delete_path('subdir/nested'): {ok3}" + (f" ({err3})" if err3 else ""))
    # ok4, err4 = client.delete_path("subdir/foo.txt")
    # print(f"delete_path('subdir/foo.txt'): {ok4}" + (f" ({err4})" if err4 else ""))
    # ok5, err5 = client.delete_path("subdir", recursive=True)
    # print(f"delete_path('subdir', recursive=True): {ok5}" + (f" ({err5})" if err5 else ""))
    # print()

    # --- path escape ---
    _section("Path escape (security)")
    p = client._resolve("../../../etc/passwd")
    print(f"_resolve('../../../etc/passwd'): {p}")
    out = client.read_file("../../../etc/passwd")
    print(f"read_file('../../../etc/passwd'): {out}")
    print()

    _section("Done")
    print(f"Root used: {TESTING_DIR}")
    print("Deletion commented out — inspect files in testing/ (subdir/, moved.txt, sample.pdf, etc.).")


if __name__ == "__main__":
    main()
