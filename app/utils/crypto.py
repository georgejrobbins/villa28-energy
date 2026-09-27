from cryptography.fernet import Fernet
import base64
import hashlib
from app.config import get_settings

def get_cipher():
    key = get_settings().encryption_key
    if not key:
        raise ValueError("Set ENCRYPTION_KEY to a generated Fernet key")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        # Support an existing Railway-generated 32+ character random secret.
        # Never accept empty/short placeholders or pad a weak key with spaces.
        if len(key) < 32 or key.startswith("your-") or len(set(key)) < 12:
            raise ValueError("ENCRYPTION_KEY must be a Fernet key or a strong random secret of at least 32 characters")
        derived = hashlib.sha256(b"villa28-energy:token-encryption:v1:" + key.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(derived))

def encryption_ready():
    try:
        get_cipher()
        return True
    except ValueError:
        return False

def encrypt_token(token):
    return get_cipher().encrypt(token.encode()).decode()

def decrypt_token(token):
    return get_cipher().decrypt(token.encode()).decode()
