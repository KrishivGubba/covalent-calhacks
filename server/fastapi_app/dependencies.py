"""
Shared dependencies for FastAPI routers.

This module provides dependency injection for the Tree, DAOs, and other shared resources.
"""
import os
import sys
import platform
from functools import lru_cache
from typing import Generator

# Add project paths
_project_root = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.abspath(_project_root))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'context-engine'))

from logger import get_logger
log = get_logger()

# SQLCipher for encrypted DB
try:
    from sqlcipher3 import dbapi2 as sqlite3
except ImportError:
    try:
        from pysqlcipher3 import dbapi2 as sqlite3
    except ImportError:
        raise ImportError(
            "SQLCipher not found. Install with: pip install sqlcipher3-wheels (macOS/Windows) or pysqlcipher3-binary (Linux)"
        )


def get_data_dir() -> str:
    """Get the user data directory for Covalent."""
    data_dir = os.environ.get('COVALENT_DATA_DIR')
    if data_dir:
        return data_dir
    if platform.system() == 'Darwin':
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Covalent")
    return os.path.join(os.path.expanduser("~"), ".covalent")


def get_db_path() -> str:
    """Get the database path from environment or default."""
    _default_db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'context-engine', 'graph.db')
    return os.environ.get('GRAPH_DB_PATH', os.path.abspath(_default_db_path))


def get_encrypted_conn(path: str = None, timeout: float = 10.0):
    """Return a connection to the encrypted database with PRAGMA key set."""
    from security.key_manager import get_db_encryption_key
    p = path or get_db_path()
    conn = sqlite3.connect(p, timeout=timeout)
    conn.execute(f"PRAGMA key = '{get_db_encryption_key()}'")
    return conn


# Lazy-loaded singletons
_tree_instance = None
_auth_dao_instance = None
_integration_dao_instance = None
_action_executor_module = None


@lru_cache()
def get_tree():
    """Get or create the Tree singleton (lazy-loaded)."""
    global _tree_instance
    if _tree_instance is None:
        from graph import Tree
        db_path = get_db_path()
        os.environ.setdefault('GRAPH_DB_PATH', db_path)
        log.info(f"📊 Initializing Tree with database: {db_path}")
        _tree_instance = Tree(db_path)
    return _tree_instance


@lru_cache()
def get_auth_dao():
    """Get or create the AuthDAO singleton."""
    global _auth_dao_instance
    if _auth_dao_instance is None:
        from auth_dao import AuthDAO
        db_path = get_db_path()
        _auth_dao_instance = AuthDAO(db_path)
        _auth_dao_instance.ensure_sessions_table()
    return _auth_dao_instance


@lru_cache()
def get_integration_dao():
    """Get or create the IntegrationDAO singleton."""
    global _integration_dao_instance
    if _integration_dao_instance is None:
        from integration_dao import IntegrationDAO
        db_path = get_db_path()
        _integration_dao_instance = IntegrationDAO(db_path)
        _integration_dao_instance.ensure_table()
    return _integration_dao_instance


def get_action_executor():
    """Lazy-load the action_executor module."""
    global _action_executor_module
    if _action_executor_module is None:
        log.info("⏳ Lazy-loading action_executor module...")
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
        import action_executor as ae
        _action_executor_module = ae
        log.info("✅ action_executor loaded")
    return _action_executor_module


# Display schema lazy loading
_display_schema_func = None
_resolve_display_fields_func = None
_is_inherited_value_func = None


def get_display_schema_func():
    """Lazy-load get_display_schema from covalent_mcp.tools."""
    global _display_schema_func
    if _display_schema_func is None:
        from covalent_mcp.tools import get_display_schema
        _display_schema_func = get_display_schema
    return _display_schema_func


def get_resolve_display_fields_func():
    """Lazy-load resolve_display_fields from covalent_mcp.toolclasses.base."""
    global _resolve_display_fields_func
    if _resolve_display_fields_func is None:
        from covalent_mcp.toolclasses.base import resolve_display_fields
        _resolve_display_fields_func = resolve_display_fields
    return _resolve_display_fields_func


def get_is_inherited_value_func():
    """Lazy-load _is_inherited_value from covalent_mcp.toolclasses.base."""
    global _is_inherited_value_func
    if _is_inherited_value_func is None:
        from covalent_mcp.toolclasses.base import _is_inherited_value
        _is_inherited_value_func = _is_inherited_value
    return _is_inherited_value_func


# FastAPI dependency functions for use with Depends()
def tree_dependency():
    """FastAPI dependency for Tree."""
    return get_tree()


def auth_dao_dependency():
    """FastAPI dependency for AuthDAO."""
    return get_auth_dao()


def integration_dao_dependency():
    """FastAPI dependency for IntegrationDAO."""
    return get_integration_dao()
