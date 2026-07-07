"""SQLAlchemy models for the Deploy domain (Docker installation registry)."""
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DeployInstallation(Base, TimestampMixin):
    """Registered Docker service/installation.

    Stores human-managed metadata (name, group, ports, links, restart_command)
    that overlays live Docker status fetched from the host-bridge at query time.
    container_name is the Docker container name used to correlate with live
    `docker ps` output from the host-bridge.

    product_id optionally links this installation to a ForgeHub Product so the
    deployment can be traced back through the full product/version/project chain.
    """

    __tablename__ = "deploy_installations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    container_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    compose_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    restart_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSONB arrays: ports → ["8000:8000"], links → [{"label":"API","url":"..."}]
    ports: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    links: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional association to a ForgeHub Product (SET NULL on delete so the
    # installation record survives product removal).
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.products.id", ondelete="SET NULL"),
        nullable=True,
    )


class DeployGroup(Base, TimestampMixin):
    """Named group used to organize DeployInstallations in the Deploy Control UI.

    Installations reference groups by name (DeployInstallation.group_name string,
    not FK) so live-docker sync and ad-hoc rows keep working without a group row.
    The API layer keeps the two in sync: renaming a group rewrites matching
    installations' group_name; deleting a group clears it (see routes/deploy.py).
    """

    __tablename__ = "deploy_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DeploySyncIgnore(Base, TimestampMixin):
    """Container names excluded from `POST /deploy/sync` auto-registration.

    When a user deletes a DeployInstallation whose container still exists in
    Docker, the sync endpoint would otherwise recreate it on the next run.
    Deleting an installation records its container_name here; manually
    re-registering the same container_name removes the entry.
    """

    __tablename__ = "deploy_sync_ignores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    container_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
