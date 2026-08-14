"""SQLAlchemy model for the Server domain (SSH-accessible infrastructure registry).

Stores the server inventory used for SSH access (name, IP, remote user,
port, description). Deliberately standalone — no cross-domain FK — since
this is an infrastructure registry, not part of the product/version/project
traceability chain covered by SPEC.md's core invariant.
"""
import uuid

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

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
    public_key: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def private_key_stored(self) -> bool:
        """Whether a durable encrypted copy of the identity file exists.
        Surfaced instead of the material itself so the key never reaches a
        response body."""
        return bool(self.private_key_encrypted)
