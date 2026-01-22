"""
Tool Modules package.

Note: Tool modules are optional and may be added/removed during development.
Keep this file import-safe: do not import non-existent tool modules here.

Add your tool modules (e.g. `weather.py`) and then import them here when they exist.
"""
from covalent_mcp.toolclasses.github import github_module
from covalent_mcp.toolclasses.google.calendar import calendar_module
from covalent_mcp.toolclasses.google.mail import gmail_module
from covalent_mcp.toolclasses.google.drive import drive_module

__all__ = ["github_module", "calendar_module", "gmail_module", "drive_module"]
