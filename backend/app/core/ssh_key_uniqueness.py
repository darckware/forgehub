"""One SSH key per machine (docs/architecture/REMOTE_ACCESS_RULE.md, rule 3).

Marcelo, 2026-11-12: "para cada estação de trabalho ou servidor vai ter uma
key diferente, para o usuário darckware". "Configurar acesso" already mints a
fresh key per machine, but a pasted key, or a vault/bridge bug, could put a
key that another machine already uses on a second row with no warning. Every
route that gives a machine a key calls `assert_key_unique` before it changes
the row.

A key is identified by its PUBLIC half: the base64 blob of the OpenSSH line,
comment ignored. A private key is reduced to its public half here (in
process, `cryptography`; never `ssh-keygen`), and the caller refuses when that
is not possible rather than skipping the check. Two rows pointing at the same
ForgeVault secret id share a key by definition, so that is refused too.

`public_key` is encrypted on the row, so the comparison runs in Python over
the other rows (tens of rows). Nothing here ever returns or logs key material:
a refusal names only the other machine.
"""
from __future__ import annotations

import base64
import binascii
import re
import uuid

from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.db.models.server import Server

CODE_IN_USE = "SSH_KEY_IN_USE"
CODE_PUBLIC_REQUIRED = "SSH_PUBLIC_KEY_REQUIRED"
CODE_PUBLIC_INVALID = "SSH_PUBLIC_KEY_INVALID"
CODE_PUBLIC_MISMATCH = "SSH_PUBLIC_KEY_MISMATCH"

# "<type> <base64> [comment]", optionally preceded by authorized_keys options
# (`from="10.0.0.1",no-pty ssh-ed25519 AAAA… c`) -- every OpenSSH public key
# type, not just the two ForgeHub generates: a stored or pasted key may be
# anything the machine accepts. The type must be a known key-type token and the
# blob must name that same type (checked below), so an option's text can't be
# mistaken for the key.
_KEY_TYPE = r"(?:ssh-(?:ed25519|rsa|dss)|ecdsa-sha2-nistp(?:256|384|521)|sk-(?:ssh-ed25519|ecdsa-sha2-nistp256)@openssh\.com|ssh-(?:ed25519|rsa)-cert-v01@openssh\.com)"
_PUBLIC_KEY = re.compile(r"(?:^|\s|,)(" + _KEY_TYPE + r")\s+([A-Za-z0-9+/]+={0,2})(?=\s|$)")


def public_key_blob(public_key: str | None) -> str | None:
    """The key's identity: its base64 blob, normalized. None when the text is
    not an OpenSSH public key line, or its blob doesn't name the declared type."""
    if not public_key or not public_key.strip():
        return None
    line = public_key.strip().splitlines()[0]
    for match in _PUBLIC_KEY.finditer(line):
        key_type, blob = match.groups()
        try:
            raw = base64.b64decode(blob, validate=True)
        except (binascii.Error, ValueError):
            continue
        # The blob starts with the key type as an SSH string (uint32 length + bytes).
        if len(raw) < 4:
            continue
        type_len = int.from_bytes(raw[:4], "big")
        if raw[4:4 + type_len] != key_type.encode():
            continue
        return base64.b64encode(raw).decode()
    return None


def derive_public_key(private_key: str, passphrase: str | None = None) -> str:
    """The OpenSSH public line (no comment) of a private key, OpenSSH or PEM.
    Raises ValueError when it can't be read: encrypted with an unknown
    passphrase, an unsupported algorithm, or not a key at all."""
    data = private_key.strip().encode() + b"\n"
    passwords: list[bytes | None] = [None]
    if passphrase:
        passwords.insert(0, passphrase.encode())
    for loader in (serialization.load_ssh_private_key, serialization.load_pem_private_key):
        for password in passwords:
            try:
                key = loader(data, password=password)
            except Exception:  # noqa: BLE001 -- wrong format/password/algorithm: try the next one
                continue
            return key.public_key().public_bytes(
                serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
            ).decode()
    raise ValueError("private key could not be read")


def _decrypted(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return decrypt_secret(value)
    except ValueError:
        return None


async def find_key_owner(
    db: AsyncSession,
    *,
    exclude_id: uuid.UUID | None,
    public_key: str | None = None,
    key_ref: str | None = None,
) -> str | None:
    """Name of another machine that already has this key (same public blob or
    same ForgeVault secret id), or None. The machine itself is excluded:
    storing its own key again is fine."""
    blob = public_key_blob(public_key)
    if not blob and not key_ref:
        return None
    query = select(Server.id, Server.name, Server.public_key_encrypted, Server.ssh_key_ref).order_by(Server.name)
    if exclude_id is not None:
        query = query.where(Server.id != exclude_id)
    for _id, name, public_encrypted, ref in (await db.execute(query)).all():
        if key_ref and ref == key_ref:
            return name
        if blob and public_key_blob(_decrypted(public_encrypted)) == blob:
            return name
    return None


def key_in_use_error(owner: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": CODE_IN_USE,
            "message": (
                f"Esta chave já é da máquina {owner}. Cada máquina tem a sua própria chave "
                "(regra 3 do acesso remoto). Use \"Configurar acesso\" para dar a esta máquina "
                "uma nova chave da conta darckware."
            ),
            "other_machine": owner,
        },
    )


async def assert_key_unique(
    db: AsyncSession,
    server_id: uuid.UUID | None,
    *,
    public_key: str | None = None,
    key_ref: str | None = None,
) -> None:
    """409 SSH_KEY_IN_USE when another machine already has this key."""
    owner = await find_key_owner(db, exclude_id=server_id, public_key=public_key, key_ref=key_ref)
    if owner:
        raise key_in_use_error(owner)


def public_key_unknown(row: Server) -> bool:
    """The key is in ForgeVault but its public half is missing, unreadable
    (doesn't decrypt) or doesn't parse: rule 3 can't compare this machine's
    key with any other until the public half is filled in."""
    return bool(row.ssh_key_ref) and public_key_blob(row.public_key) is None


def duplicate_keys_by_server(rows: list[Server]) -> dict[uuid.UUID, list[str]]:
    """Read-only report of keys already shared by several rows (before this
    rule existed): for each row, the other machines with the same public key,
    the same ForgeVault secret id or the same key file. Never changes data."""
    groups: dict[tuple[str, str], list[Server]] = {}
    for row in rows:
        blob = public_key_blob(row.public_key)
        for marker in (("pub", blob), ("ref", row.ssh_key_ref), ("path", row.ssh_key_path)):
            if marker[1]:
                groups.setdefault(marker, []).append(row)
    out: dict[uuid.UUID, list[str]] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        for row in members:
            names = out.setdefault(row.id, [])
            for other in members:
                if other.id != row.id and other.name not in names:
                    names.append(other.name)
    return {key: sorted(value) for key, value in out.items()}
