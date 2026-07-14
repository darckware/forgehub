"""Small encryption boundary for application-managed credentials."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    # JWT_SECRET is already required to remain stable and secret. Deriving a
    # distinct fixed-size key avoids introducing a second deployment secret.
    digest = hashlib.sha256(f"forgehub-credentials:{settings.JWT_SECRET}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Stored credential cannot be decrypted") from exc
