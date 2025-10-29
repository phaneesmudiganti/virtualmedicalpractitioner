import base64, os, json
from cryptography.fernet import Fernet
from core.config import settings

def _derive_key(secret: str) -> bytes:
    # Expect base64 urlsafe key. If not provided as base64, derive.
    try:
        base64.urlsafe_b64decode(secret)
        return secret.encode()
    except Exception:
        padded = (secret + ("0" * 32))[:32].encode()  # naive pad to 32 bytes
        return base64.urlsafe_b64encode(padded)

fernet = Fernet(_derive_key(settings.SECRET_KEY or Fernet.generate_key().decode()))

def encrypt_json(obj) -> bytes:
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return fernet.encrypt(data)

def decrypt_json(blob: bytes):
    data = fernet.decrypt(blob)
    return json.loads(data.decode("utf-8"))