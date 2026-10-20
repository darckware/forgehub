"""Encrypt the server public key at rest, and add the key passphrase

Two columns replace one (2026-08-14, Marcelo: "a chave publica precisa de
criptografada no banco de dados" and "preciso adicionar o campo de senha na
chave publica no cadastro do Servers"):

  public_key            -> public_key_encrypted      (backfilled, then dropped)
  (new) key_passphrase_encrypted

The backfill runs through core/secrets.py's Fernet rather than raw SQL,
because the ciphertext must be readable by the same helper the model uses --
which means this migration needs the app's JWT_SECRET to be the one the rows
will later be read with. Rotating that secret makes public keys unreadable
(the model degrades them to NULL rather than failing the listing) and
passphrases undecryptable, exactly like the private-key vault added in
a7c31e9b2d40.

The drop is the point: keeping the cleartext column alongside the encrypted
one would leave the very copy this change exists to remove.

Revision ID: e2f4a71b9c53
Revises: a7c31e9b2d40
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op

from app.core.secrets import decrypt_secret, encrypt_secret

revision = "e2f4a71b9c53"
down_revision = "a7c31e9b2d40"
branch_labels = None
depends_on = None

# Literal, like every other migration in this directory.
SCHEMA = "company"


def upgrade() -> None:
    op.add_column(
        "servers",
        sa.Column("public_key_encrypted", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "servers",
        sa.Column("key_passphrase_encrypted", sa.Text(), nullable=True),
        schema=SCHEMA,
    )

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(f"SELECT id, public_key FROM {SCHEMA}.servers WHERE public_key IS NOT NULL")
    ).fetchall()
    for row_id, public_key in rows:
        if not public_key:
            continue
        conn.execute(
            sa.text(
                f"UPDATE {SCHEMA}.servers SET public_key_encrypted = :value WHERE id = :id"
            ),
            {"value": encrypt_secret(public_key), "id": row_id},
        )

    op.drop_column("servers", "public_key", schema=SCHEMA)


def downgrade() -> None:
    op.add_column("servers", sa.Column("public_key", sa.Text(), nullable=True), schema=SCHEMA)

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            f"SELECT id, public_key_encrypted FROM {SCHEMA}.servers "
            "WHERE public_key_encrypted IS NOT NULL"
        )
    ).fetchall()
    for row_id, encrypted in rows:
        if not encrypted:
            continue
        try:
            plain = decrypt_secret(encrypted)
        except ValueError:
            # An unreadable value cannot be un-encrypted; leaving it NULL is
            # honest, and the encrypted column is dropped right after anyway.
            continue
        conn.execute(
            sa.text(f"UPDATE {SCHEMA}.servers SET public_key = :value WHERE id = :id"),
            {"value": plain, "id": row_id},
        )

    op.drop_column("servers", "public_key_encrypted", schema=SCHEMA)
    op.drop_column("servers", "key_passphrase_encrypted", schema=SCHEMA)
