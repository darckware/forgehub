"""SQLAlchemy model for the Server domain (SSH-accessible infrastructure registry).

Stores the server inventory used for SSH access (name, IP, remote user,
port, description). Deliberately standalone — no cross-domain FK — since
this is an infrastructure registry, not part of the product/version/project
traceability chain covered by SPEC.md's core invariant.
"""
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import true as sa_true
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.secrets import decrypt_secret, encrypt_secret
from app.db.base import Base, TimestampMixin


class Server(Base, TimestampMixin):
    __tablename__ = "servers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    ip_address: Mapped[str] = mapped_column(String(100), nullable=False)
    remote_user: Mapped[str] = mapped_column(String(100), nullable=False)
    ssh_port: Mapped[int] = mapped_column(Integer, nullable=False, default=22, server_default="22")
    # Path (on the host running the terminal's bash/PTY) to the SSH identity
    # file used for public-key auth with this server, e.g.
    # "/root/.ssh/id_ed25519_aegis" -- passed as `ssh -i <path>`. Optional:
    # falls back to the shell's default identity/agent when unset.
    ssh_key_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Public half of the dedicated key installed on the server's
    # authorized_keys by the "install SSH key" flow (see
    # /servers/{id}/install-key) -- kept on the row for auditing/re-install.
    #
    # Encrypted at rest like the private half (2026-08-14, Marcelo: "a chave
    # publica precisa de criptografada no banco de dados"), even though a
    # public key is not secret material -- the same value sits in cleartext in
    # the server's own authorized_keys. It is still *returned* decrypted by
    # every read, since the screen exists to show and copy it; the `public_key`
    # property below is what ServerOut serializes.
    public_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Private half, Fernet-encrypted (core/secrets.py, same boundary as
    # Agent.forgerouter_api_key_encrypted). A durable copy, NOT the copy ssh
    # uses: the terminal always runs `ssh -i <ssh_key_path>` against the file
    # on the host, and this column is what lets that file be rebuilt when it
    # disappears.
    #
    # It exists because that is not hypothetical (2026-08-14, Marcelo: "seria
    # melhor criptografar a chave no banco de dados para não perder"): the
    # Aegis profile directory was recreated on 2026-07-07 and the keys for
    # 172.15.2.4/172.15.2.5 survived only inside
    # /root/agents/aegis.backup.1783020451, so ForgeHub's terminal could no
    # longer reach srv-sup/srv-app05 at all. The inventory row knew the path;
    # nothing knew the key. Storing a path is not storing a key.
    #
    # Never returned by any endpoint -- ServerOut exposes only the boolean
    # `private_key_stored`. Written by /servers/{id}/key:backup (read from the
    # host) or PUT /servers/{id}/key (pasted); poured back onto the host by
    # /servers/{id}/key:restore.
    private_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Passphrase protecting the identity file, Fernet-encrypted. Stored beside
    # the key it unlocks on purpose: a vaulted key whose passphrase lives only
    # in someone's head is not a recoverable key, which is the whole point of
    # the vault. Unlike the key, it is NEVER returned by any endpoint -- the
    # `key_passphrase_stored` boolean is all a response carries.
    #
    # Consumed by the in-container paramiko probe (_probe_ssh). The host-bridge
    # probe and the Workspace terminal both shell out to `ssh`, which cannot be
    # handed a passphrase non-interactively without an agent, so they are
    # unaffected by this column -- see check_server_status.
    key_passphrase_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether ForgeHub may use this server at all: the status probe skips it
    # and the Workspace terminal refuses to open (2026-08-14, Marcelo: "tem um
    # forma de adicionar um icone de ligar/desligar o acesso, sem excluir a
    # chave").
    #
    # A ForgeHub-side switch, not a remote one: nothing is revoked on the
    # server, the identity file is untouched, and the vaulted copy stays --
    # which is the point. Deleting the key to stop using a machine for a while
    # is what this exists to avoid. Revoking access *on the server* means
    # editing its authorized_keys, which this flag deliberately does not do.
    access_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa_true()
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def private_key_stored(self) -> bool:
        """Whether a durable encrypted copy of the identity file exists.
        Surfaced instead of the material itself so the key never reaches a
        response body."""
        return bool(self.private_key_encrypted)

    @property
    def key_passphrase_stored(self) -> bool:
        """Whether a passphrase is on file. The passphrase itself is never
        serialized -- this boolean is what tells the form whether to render
        "stored" or an empty field."""
        return bool(self.key_passphrase_encrypted)

    @property
    def public_key(self) -> str | None:
        """The installed public key, decrypted. What ServerOut serializes.

        Degrades to None rather than raising when the stored value cannot be
        decrypted (a rotated JWT_SECRET): a public key is a convenience for
        copy-paste, and one unreadable row must not take the whole inventory
        listing down with it. The private key and passphrase deliberately do
        NOT degrade this way -- there, failing loudly is the correct answer.
        """
        if not self.public_key_encrypted:
            return None
        try:
            return decrypt_secret(self.public_key_encrypted)
        except ValueError:
            return None

    @public_key.setter
    def public_key(self, value: str | None) -> None:
        self.public_key_encrypted = encrypt_secret(value) if value else None


# Scheme is a plain String + CheckConstraint, not a native ENUM -- the
# convention stated in db/base.py (keeps migrations free of ALTER TYPE churn).
SERVER_SERVICE_SCHEMES = ("http", "https")


class ServerService(Base, TimestampMixin):
    """A web service reachable on one of a server's ports.

    Exists so the inventory answers "what runs here, and where do I open it"
    (2026-08-14, Marcelo: "preciso ao clicar na linha abri o link dos serviços
    de cada servidor... Exemplo: 172.15.2.3:8000"). The row stores only the
    port and how to address it -- the host comes from the parent Server, so
    changing a server's IP moves every one of its services with it instead of
    leaving a set of stale URLs behind.

    Registered by hand, and optionally discovered: the scan endpoint reports
    which ports actually answer, but never writes a row on its own. A port
    being open is not a claim about what is behind it, and a list that invents
    its own entries stops being a record of what someone meant to publish.
    """

    __tablename__ = "server_services"
    __table_args__ = (
        # One entry per (server, port, path): the same port can legitimately
        # host two documented entry points under different paths.
        #
        # NULLS NOT DISTINCT is the whole point (Postgres 15+): a plain UNIQUE
        # treats every NULL as distinct, so the common case -- no path at all
        # -- would accept the same port twice over, which is exactly the
        # duplicate this constraint exists to stop.
        UniqueConstraint(
            "server_id",
            "port",
            "path",
            name="uq_server_service_endpoint",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "scheme IN ('http', 'https')", name="ck_server_services_scheme"
        ),
        CheckConstraint("port BETWEEN 1 AND 65535", name="ck_server_services_port"),
        Index("ix_server_services_server_id", "server_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Cascade: a service cannot outlive the machine it runs on, and the row
    # carries no history worth keeping once the server is gone.
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.servers.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    scheme: Mapped[str] = mapped_column(String(10), nullable=False, default="http", server_default="http")
    # Optional path under the port, e.g. "/admin". Stored without the leading
    # host so the URL is always rebuilt from the parent's current address.
    path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
