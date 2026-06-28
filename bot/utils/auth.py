from cryptography.fernet import Fernet
from typing import Dict
from hsr_cards.models.auth import Cookies

from bot.config.config import FERNET_KEY

cipher=Fernet(
    FERNET_KEY.encode()
)

def encrypt_token(token:str)->str:
    return cipher.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token:str)-> Cookies:
    token=cipher.decrypt(encrypted_token.encode()).decode()
    token=token.split("||")
    return Cookies(
        ltoken_v2=token[0],
        ltuid_v2=token[1]
    )