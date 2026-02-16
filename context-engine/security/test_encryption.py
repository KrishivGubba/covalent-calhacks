#!/usr/bin/env python3
"""
Test script to verify database encryption is working correctly.

Tests:
1. Key generation and Keychain storage
2. File permissions are secure
3. Database is encrypted (can't read with standard sqlite3)
4. Encrypted database operations work with SQLCipher
5. Unencrypted access is properly denied

Usage:
    python context-engine/security/test_encryption.py
    
    # Or to test a specific database:
    python context-engine/security/test_encryption.py /path/to/database.db
"""

import os
import sys
import tempfile
import sqlite3 as stdlib_sqlite3  # Standard library sqlite3 (unencrypted)

# Add context-engine to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from security.key_manager import get_db_encryption_key, delete_key, key_exists
from security.validation import (
    check_database_permissions,
    verify_encryption,
    check_keychain_access,
    run_security_checks
)


def print_header(title: str) -> None:
    """Print a formatted test section header."""
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print('=' * 50)


def print_result(success: bool, message: str) -> None:
    """Print a test result."""
    icon = "✅" if success else "❌"
    print(f"   {icon} {message}")


def test_key_management() -> bool:
    """Test 1: Key generation and Keychain storage."""
    print_header("1. Key Management")
    
    try:
        # Test key retrieval (creates if doesn't exist)
        print("\n   Testing key retrieval...")
        key = get_db_encryption_key()
        
        if not key:
            print_result(False, "Key retrieval returned empty key")
            return False
        
        print_result(True, f"Key retrieved successfully (length: {len(key)} chars)")
        
        # Test key existence check
        print("\n   Testing key existence check...")
        exists = key_exists()
        
        if not exists:
            print_result(False, "key_exists() returned False after key retrieval")
            return False
        
        print_result(True, "Key exists in Keychain")
        
        # Test consistent key retrieval
        print("\n   Testing consistent key retrieval...")
        key2 = get_db_encryption_key()
        
        if key != key2:
            print_result(False, "Key retrieval returned different keys!")
            return False
        
        print_result(True, "Consistent key retrieval confirmed")
        
        return True
        
    except Exception as e:
        print_result(False, f"Key management test failed: {e}")
        return False


def test_database_creation() -> tuple:
    """Test 2: Create encrypted database."""
    print_header("2. Database Creation")
    
    try:
        from sqlcipher3 import dbapi2 as sqlite3
    except ImportError:
        try:
            from pysqlcipher3 import dbapi2 as sqlite3
        except ImportError:
            print_result(False, "SQLCipher not installed (pip install sqlcipher3-wheels)")
            return False, None
    
    # Create temp database file
    temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    temp_db.close()
    db_path = temp_db.name
    
    try:
        print(f"\n   Creating temp database: {db_path}")
        
        # Get encryption key
        key = get_db_encryption_key()
        
        # Create encrypted database
        conn = sqlite3.connect(db_path)
        conn.execute(f"PRAGMA key = '{key}'")
        
        # Create test table
        conn.execute("""
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                secret_data TEXT
            )
        """)
        
        # Insert test data
        conn.execute(
            "INSERT INTO test_table (secret_data) VALUES (?)",
            ("This is sensitive data that should be encrypted!",)
        )
        conn.commit()
        conn.close()
        
        # Set secure permissions
        os.chmod(db_path, 0o600)
        
        print_result(True, "Encrypted database created successfully")
        
        return True, db_path
        
    except Exception as e:
        print_result(False, f"Database creation failed: {e}")
        if os.path.exists(db_path):
            os.unlink(db_path)
        return False, None


def test_file_permissions(db_path: str) -> bool:
    """Test 3: Check file permissions."""
    print_header("3. File Permissions")
    
    result = check_database_permissions(db_path)
    
    if result["status"] == "secure":
        print_result(True, result["message"])
        return True
    elif result["status"] == "warning":
        print_result(False, f"Warning: {result['message']}")
        return True
    else:
        print_result(False, result["message"])
        return False


def test_encryption_verification(db_path: str) -> bool:
    """Test 4: Verify database is encrypted."""
    print_header("4. Encryption Verification")
    
    result = verify_encryption(db_path)
    
    if result["status"] == "encrypted":
        print_result(True, result["message"])
        return True
    elif result["status"] == "unencrypted":
        print_result(False, f"SECURITY RISK: {result['message']}")
        return False
    else:
        print_result(False, f"Error: {result['message']}")
        return False


def test_encrypted_access(db_path: str) -> bool:
    """Test 5: Verify encrypted database access works."""
    print_header("5. Encrypted Access")
    
    try:
        from sqlcipher3 import dbapi2 as sqlite3
    except ImportError:
        try:
            from pysqlcipher3 import dbapi2 as sqlite3
        except ImportError:
            print_result(False, "SQLCipher not installed (pip install sqlcipher3-wheels)")
            return False
    
    try:
        # Get key and connect
        key = get_db_encryption_key()
        conn = sqlite3.connect(db_path)
        conn.execute(f"PRAGMA key = '{key}'")
        
        # Read test data
        cursor = conn.execute("SELECT secret_data FROM test_table LIMIT 1")
        row = cursor.fetchone()
        
        if not row:
            print_result(False, "No data found in encrypted database")
            conn.close()
            return False
        
        secret_data = row[0]
        print_result(True, f"Successfully read encrypted data: '{secret_data[:30]}...'")
        
        conn.close()
        return True
        
    except Exception as e:
        print_result(False, f"Encrypted access failed: {e}")
        return False


def test_unencrypted_access_denied(db_path: str) -> bool:
    """Test 6: Verify unencrypted access is denied."""
    print_header("6. Unencrypted Access Denied")
    
    try:
        # Try to open with standard sqlite3 (no encryption)
        conn = stdlib_sqlite3.connect(db_path)
        
        # Try to read data
        conn.execute("SELECT * FROM test_table LIMIT 1")
        conn.close()
        
        # If we got here, database is NOT encrypted!
        print_result(False, "SECURITY RISK: Database readable without encryption key!")
        return False
        
    except stdlib_sqlite3.DatabaseError as e:
        # This is expected - database should be unreadable
        print_result(True, f"Unencrypted access properly denied: {type(e).__name__}")
        return True
        
    except Exception as e:
        print_result(False, f"Unexpected error: {e}")
        return False


def test_keychain_access() -> bool:
    """Test 7: Verify Keychain access."""
    print_header("7. Keychain Access")
    
    result = check_keychain_access()
    
    if result["status"] == "accessible":
        print_result(True, result["message"])
        return True
    else:
        print_result(False, result["message"])
        return False


def run_all_tests(db_path: str = None) -> bool:
    """Run all encryption tests."""
    print("\n🧪 Database Encryption Test Suite")
    print("=" * 50)
    
    results = []
    temp_db_path = None
    
    # Test 1: Key management
    results.append(("Key Management", test_key_management()))
    
    # Test 2: Database creation (if no db_path provided)
    if db_path is None:
        success, temp_db_path = test_database_creation()
        results.append(("Database Creation", success))
        
        if not success:
            print("\n❌ Cannot continue tests without database")
            return False
        
        db_path = temp_db_path
    else:
        results.append(("Database Creation", True))
    
    try:
        # Test 3: File permissions
        results.append(("File Permissions", test_file_permissions(db_path)))
        
        # Test 4: Encryption verification
        results.append(("Encryption Verification", test_encryption_verification(db_path)))
        
        # Test 5: Encrypted access
        results.append(("Encrypted Access", test_encrypted_access(db_path)))
        
        # Test 6: Unencrypted access denied
        results.append(("Unencrypted Access Denied", test_unencrypted_access_denied(db_path)))
        
        # Test 7: Keychain access
        results.append(("Keychain Access", test_keychain_access()))
        
    finally:
        # Cleanup temp database
        if temp_db_path and os.path.exists(temp_db_path):
            print(f"\n🗑️  Cleaning up temp database: {temp_db_path}")
            os.unlink(temp_db_path)
    
    # Print summary
    print_header("Test Summary")
    
    all_passed = True
    for name, passed in results:
        icon = "✅" if passed else "❌"
        print(f"   {icon} {name}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 All tests passed! Database encryption is working correctly.")
    else:
        print("⚠️  Some tests failed. Review output above for details.")
    
    return all_passed


if __name__ == "__main__":
    # Optional: specify database path as command line argument
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    success = run_all_tests(db_path)
    sys.exit(0 if success else 1)
