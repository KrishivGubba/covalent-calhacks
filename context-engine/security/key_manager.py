"""
Database Encryption Key Manager.

Manages encryption keys for SQLCipher database encryption using macOS Keychain.

Key is stored in:
- Service: com.covalent.db_encryption
- Account: graph_db_key

Usage:
    from security.key_manager import get_db_encryption_key
    
    key = get_db_encryption_key()  # Gets existing key or generates new one
"""

import secrets
import logging

try:
    import keyring
except ImportError:
    raise ImportError(
        "keyring package not installed. "
        "Install with: pip install keyring"
    )


# Keychain service and account names
SERVICE_NAME = "com.covalent.db_encryption"
ACCOUNT_NAME = "graph_db_key"

# Key length in bytes (32 bytes = 256 bits for AES-256)
KEY_LENGTH_BYTES = 32


def get_db_encryption_key() -> str:
    """
    Get or create database encryption key from macOS Keychain.
    
    On first run, generates a new 64-character hex key (32 bytes) 
    and stores it in the Keychain. On subsequent runs, retrieves 
    the existing key.
    
    Returns:
        str: 64-character hex string encryption key
    
    Raises:
        keyring.errors.KeyringError: If Keychain access fails
    """
    key = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
    
    if key is None:
        # Generate new 64-character hex key (32 bytes = 256 bits)
        key = secrets.token_hex(KEY_LENGTH_BYTES)
        keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, key)
        logging.info(f"🔑 Generated new encryption key and stored in Keychain")
        print(f"🔑 Generated new encryption key and stored in Keychain")
    
    return key


def delete_key() -> bool:
    """
    Delete encryption key from Keychain.
    
    Used for reset/cleanup operations. After deletion, 
    the next call to get_db_encryption_key() will generate 
    a new key.
    
    WARNING: Deleting the key will make existing encrypted 
    databases unreadable!
    
    Returns:
        bool: True if key was deleted, False if key didn't exist
    """
    try:
        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
        logging.info("🗑️  Deleted encryption key from Keychain")
        print("🗑️  Deleted encryption key from Keychain")
        return True
    except keyring.errors.PasswordDeleteError:
        logging.warning("No encryption key found in Keychain to delete")
        return False


def key_exists() -> bool:
    """
    Check if encryption key exists in Keychain.
    
    Returns:
        bool: True if key exists, False otherwise
    """
    key = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
    return key is not None


def rotate_key(db_path: str) -> bool:
    """
    Rotate the encryption key (for future use).
    
    This requires re-encrypting the database with a new key.
    Currently not implemented - placeholder for future security enhancement.
    
    Args:
        db_path: Path to the encrypted database
    
    Returns:
        bool: True if rotation succeeded, False otherwise
    
    Note:
        Key rotation requires using SQLCipher's PRAGMA rekey command
        which re-encrypts the database with a new key.
    """
    # Placeholder for future implementation
    # Implementation would:
    # 1. Generate new key
    # 2. Open database with old key
    # 3. Execute PRAGMA rekey = 'new_key'
    # 4. Store new key in Keychain
    # 5. Delete old key
    raise NotImplementedError(
        "Key rotation not yet implemented. "
        "To rotate key manually: delete database, delete key from Keychain, "
        "and run init_db.py to create new encrypted database."
    )
