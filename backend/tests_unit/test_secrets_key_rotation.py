"""SECRETS_ENCRYPTION_KEY lets JWT_SECRET rotate without losing stored credentials."""
from app.core import secrets
from app.core.config import settings


def test_encryption_key_survives_jwt_rotation(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "old-jwt-secret-value")
    monkeypatch.setattr(settings, "SECRETS_ENCRYPTION_KEY", "")
    stored = secrets.encrypt_secret("fr-key")

    # Rotation: the old JWT secret becomes the encryption key material.
    monkeypatch.setattr(settings, "JWT_SECRET", "a-brand-new-jwt-secret")
    monkeypatch.setattr(settings, "SECRETS_ENCRYPTION_KEY", "old-jwt-secret-value")
    assert secrets.decrypt_secret(stored) == "fr-key"


def test_empty_encryption_key_still_derives_from_jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "only-jwt")
    monkeypatch.setattr(settings, "SECRETS_ENCRYPTION_KEY", "")
    stored = secrets.encrypt_secret("x")
    monkeypatch.setattr(settings, "SECRETS_ENCRYPTION_KEY", "only-jwt")
    assert secrets.decrypt_secret(stored) == "x"
