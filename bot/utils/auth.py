"""Compatibility imports for the shared credential cipher."""

from shared.auth.crypto import (
    decrypt_str,
    decrypt_token,
    encrypt_str,
    encrypt_token,
)

__all__ = ["decrypt_str", "decrypt_token", "encrypt_str", "encrypt_token"]