"""
Security module for database encryption and key management.

Provides:
- key_manager: Encryption key generation and macOS Keychain storage
- validation: Runtime security checks for database encryption and permissions
"""

from security.key_manager import get_db_encryption_key, delete_key, key_exists
from security.validation import (
    run_security_checks,
    check_database_permissions,
    verify_encryption,
    check_keychain_access,
    fix_permissions
)

__all__ = [
    # Key management
    "get_db_encryption_key",
    "delete_key",
    "key_exists",
    # Validation
    "run_security_checks",
    "check_database_permissions",
    "verify_encryption",
    "check_keychain_access",
    "fix_permissions"
]
