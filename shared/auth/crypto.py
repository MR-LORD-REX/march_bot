from __future__ import annotations

from cryptography.fernet import Fernet
from hsr_cards.models.auth import Cookies

from shared.config.settings import FERNET_KEY

cipher = Fernet(FERNET_KEY.encode())


def encrypt_token(token: str) -> str:
    return cipher.encrypt(token.encode()).decode()


def encrypt_str(value: str) -> str:
    """Encrypt an arbitrary secret (for example an API key)."""
    return cipher.encrypt(value.encode()).decode()


def decrypt_str(value: str) -> str:
    return cipher.decrypt(value.encode()).decode()


def decrypt_token(encrypted_token: str) -> Cookies:
    token = cipher.decrypt(encrypted_token.encode()).decode().split("||")
    return Cookies(ltoken_v2=token[0], ltuid_v2=token[1])