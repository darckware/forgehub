"""TOTP (Time-based One-Time Password) helpers for two-factor authentication."""
import base64
import io
import secrets
import string

import bcrypt
import pyotp
import qrcode  # type: ignore[import-untyped]
import qrcode.constants  # type: ignore[import-untyped]

APP_NAME = "ForgeHub"


def generate_totp_secret() -> str:
    """Return a new random base32-encoded TOTP secret."""
    return pyotp.random_base32()


def generate_provisioning_uri(secret: str, username: str) -> str:
    """Return an ``otpauth://`` provisioning URI for authenticator apps."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=APP_NAME)


def generate_qr_code_data_url(uri: str) -> str:
    """Return a ``data:image/png;base64,...`` QR-code image for *uri*."""
    img = qrcode.make(uri, error_correction=qrcode.constants.ERROR_CORRECT_L)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def verify_totp_code(secret: str, code: str) -> bool:
    """Check a 6-digit TOTP *code* against *secret* (±2 time-step window = ±60s)."""
    if not secret or not code:
        return False
    clean_code = code.strip().replace(" ", "")
    totp = pyotp.TOTP(secret)
    return totp.verify(clean_code, valid_window=2)


def generate_recovery_codes(count: int = 8) -> list[str]:
    """Return *count* random 8-character recovery codes."""
    alphabet = string.ascii_uppercase + string.digits
    return [
        "".join(secrets.choice(alphabet) for _ in range(8))
        for _ in range(count)
    ]


def hash_recovery_code(code: str) -> str:
    """Bcrypt-hash a single recovery code for database storage."""
    clean = code.strip().replace("-", "").replace(" ", "").upper()
    return bcrypt.hashpw(clean.encode(), bcrypt.gensalt()).decode()


def verify_recovery_code(code: str, hashed: str) -> bool:
    """Check a plain recovery code against a bcrypt hash."""
    clean = code.strip().replace("-", "").replace(" ", "").upper()
    try:
        return bcrypt.checkpw(clean.encode(), hashed.encode())
    except (TypeError, ValueError):
        return False
