"""
Runtime security validation for database encryption.

Provides functions to verify:
- Database file permissions are secure
- Database is properly encrypted
- Encryption key is accessible from Keychain

Usage:
    from security.validation import run_security_checks
    
    run_security_checks("/path/to/graph.db")
"""

import os
import stat
import sqlite3 as stdlib_sqlite3  # Standard library sqlite3 for testing unencrypted access
from pathlib import Path
from typing import Dict, Any


def check_database_permissions(db_path: str) -> Dict[str, Any]:
    """
    Verify database file has secure permissions.
    
    Args:
        db_path: Path to the database file
    
    Returns:
        Dict with 'status' ('secure', 'insecure', 'missing') and details
    """
    if not os.path.exists(db_path):
        return {
            "status": "missing",
            "message": "Database file not found",
            "path": db_path
        }
    
    st = os.stat(db_path)
    mode = stat.S_IMODE(st.st_mode)
    
    # Check if permissions are too permissive
    # Secure permissions should be 0o600 (owner read/write only)
    if mode & 0o077:  # Check if group or other has any permissions
        return {
            "status": "insecure",
            "message": f"Database has insecure permissions: {oct(mode)}",
            "current_mode": oct(mode),
            "recommended_mode": "0o600",
            "fix": f"Run: chmod 600 {db_path}"
        }
    
    if mode != 0o600:
        return {
            "status": "warning",
            "message": f"Database permissions are {oct(mode)}, recommended is 0o600",
            "current_mode": oct(mode),
            "recommended_mode": "0o600"
        }
    
    return {
        "status": "secure",
        "message": "Database permissions OK (0o600)",
        "current_mode": oct(mode)
    }


def verify_encryption(db_path: str) -> Dict[str, Any]:
    """
    Verify database is encrypted by attempting to read without key.
    
    Uses standard library sqlite3 (not SQLCipher) to attempt to open
    the database. If it succeeds, the database is NOT encrypted.
    If it fails with DatabaseError, the database IS encrypted.
    
    Args:
        db_path: Path to the database file
    
    Returns:
        Dict with 'status' ('encrypted', 'unencrypted', 'missing') and details
    """
    if not os.path.exists(db_path):
        return {
            "status": "missing",
            "message": "Database file not found",
            "path": db_path
        }
    
    try:
        # Try to open database WITHOUT encryption key using standard sqlite3
        conn = stdlib_sqlite3.connect(db_path)
        
        # Try to read from sqlite_master table
        conn.execute("SELECT name FROM sqlite_master LIMIT 1")
        conn.close()
        
        # If we got here, the database is NOT encrypted!
        return {
            "status": "unencrypted",
            "message": "WARNING: Database is NOT encrypted! Data is readable without key.",
            "risk": "HIGH - Sensitive data (OAuth tokens, user sessions) may be exposed"
        }
        
    except stdlib_sqlite3.DatabaseError as e:
        # Database is encrypted - standard sqlite3 cannot read it
        error_msg = str(e).lower()
        if "encrypted" in error_msg or "not a database" in error_msg or "malformed" in error_msg:
            return {
                "status": "encrypted",
                "message": "Database is properly encrypted (SQLCipher)",
                "verified": True
            }
        else:
            return {
                "status": "error",
                "message": f"Unexpected database error: {e}",
                "error": str(e)
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to verify encryption: {e}",
            "error": str(e)
        }


def check_keychain_access() -> Dict[str, Any]:
    """
    Verify encryption key is accessible from macOS Keychain.
    
    Returns:
        Dict with 'status' ('accessible', 'error') and details
    """
    try:
        from security.key_manager import get_db_encryption_key, key_exists, SERVICE_NAME, ACCOUNT_NAME
        
        # Check if key exists
        if not key_exists():
            return {
                "status": "missing",
                "message": "No encryption key found in Keychain. Run init_db.py to create one.",
                "service": SERVICE_NAME,
                "account": ACCOUNT_NAME
            }
        
        # Try to retrieve the key
        key = get_db_encryption_key()
        
        if not key:
            return {
                "status": "error",
                "message": "Key exists but could not be retrieved",
                "service": SERVICE_NAME,
                "account": ACCOUNT_NAME
            }
        
        return {
            "status": "accessible",
            "message": "Encryption key retrieved successfully from Keychain",
            "service": SERVICE_NAME,
            "account": ACCOUNT_NAME,
            "key_length": len(key)
        }
        
    except ImportError as e:
        return {
            "status": "error",
            "message": f"Failed to import key_manager: {e}",
            "error": str(e)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to access Keychain: {e}",
            "error": str(e)
        }


def run_security_checks(db_path: str, verbose: bool = True) -> Dict[str, Any]:
    """
    Run all security checks and return results.
    
    Args:
        db_path: Path to the database file
        verbose: If True, print results to console
    
    Returns:
        Dict with results of all checks
    """
    results = {
        "overall_status": "unknown",
        "checks": {}
    }
    
    if verbose:
        print("\n🔒 Running Security Checks...")
        print("=" * 50)
    
    # Check 1: File permissions
    perm_result = check_database_permissions(db_path)
    results["checks"]["permissions"] = perm_result
    
    if verbose:
        status_icon = "✅" if perm_result["status"] == "secure" else "⚠️" if perm_result["status"] == "warning" else "❌"
        print(f"\n1. File Permissions:")
        print(f"   {status_icon} {perm_result['message']}")
    
    # Check 2: Database encryption
    enc_result = verify_encryption(db_path)
    results["checks"]["encryption"] = enc_result
    
    if verbose:
        status_icon = "✅" if enc_result["status"] == "encrypted" else "❌"
        print(f"\n2. Database Encryption:")
        print(f"   {status_icon} {enc_result['message']}")
    
    # Check 3: Keychain access
    key_result = check_keychain_access()
    results["checks"]["keychain"] = key_result
    
    if verbose:
        status_icon = "✅" if key_result["status"] == "accessible" else "❌"
        print(f"\n3. Keychain Access:")
        print(f"   {status_icon} {key_result['message']}")
    
    # Determine overall status
    all_ok = (
        perm_result["status"] in ("secure", "warning") and
        enc_result["status"] == "encrypted" and
        key_result["status"] == "accessible"
    )
    
    results["overall_status"] = "secure" if all_ok else "issues_found"
    
    if verbose:
        print("\n" + "=" * 50)
        if all_ok:
            print("✅ All security checks passed!")
        else:
            print("⚠️  Security issues found - review above warnings")
        print()
    
    return results


def fix_permissions(db_path: str) -> bool:
    """
    Fix database file permissions to secure mode (0o600).
    
    Args:
        db_path: Path to the database file
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not os.path.exists(db_path):
            print(f"❌ Database file not found: {db_path}")
            return False
        
        os.chmod(db_path, 0o600)
        print(f"✅ Fixed permissions on {db_path} to 0o600")
        return True
        
    except Exception as e:
        print(f"❌ Failed to fix permissions: {e}")
        return False


if __name__ == "__main__":
    import sys
    
    # Default database path
    db_path = os.path.join(os.path.dirname(__file__), "..", "graph.db")
    
    # Allow override via command line argument
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    print(f"📂 Checking database: {db_path}")
    results = run_security_checks(db_path)
    
    # Exit with error code if issues found
    sys.exit(0 if results["overall_status"] == "secure" else 1)
