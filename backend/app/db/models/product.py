"""SQLAlchemy models for the Product domain.

Tables owned by this domain (SPEC.md section 4.1 / 6.1):
- products
- product_modules
- product_versions
- releases

Business rules encoded here (SPEC.md section 6.1):
1. Every product must have a unique name        -> unique=True on Product.name
2. Every product can have many modules          -> ProductModule.product_id FK
3. Every product must have at least one version -> enforced at the API layer
   (cannot be a DB constraint since the first version must be created in a
   second statement after the product exists); see app/api/routes/product.py
   create_product, which creates an initial ProductVersion in the same
   transaction.
4. Published versions cannot be mutated directly -> enforced at the API layer
   via ProductVersion.status; see app/api/routes/product.py update_version.
5. Fixes for published versions must create patch/hotfix flows -> out of
   scope for this domain's CRUD surface (belongs to the Backlog/Planning
   domain's PlanningItem/Release flow); ProductVersion.status supports a
   "deprecated" value and Release links a version to a published artifact
   set so future domains can build patch/hotfix flows on top of it.

Cross-domain references: projects.project_versions etc. belong to OTHER
domains (Project domain) and are not modeled here. Any future FK from
another domain's table back to product_versions.id must use a string-based
ForeignKey("company.product_versions.id") to avoid import coupling, per
foundation convention.
"""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# Allowed values for ProductVersion.status. Encoded as a CHECK constraint
# (not a Postgres ENUM) to keep migrations simple or use plain `String` to
# keep this domain self-contained without an enum-type migration.
PRODUCT_VERSION_STATUSES = ("planned", "in_development", "in_test", "published", "deprecated")

# Allowed values for Release.status.
RELEASE_STATUSES = ("draft", "ready", "released", "cancelled")

# Allowed values for Product.status.
PRODUCT_STATUSES = ("active", "inactive", "archived")


class Product(Base, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(f"status IN {PRODUCT_STATUSES!r}", name="ck_products_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", server_default="active")

    # Kanboard project created when this product is registered.
    # kanboard_column_ids maps ForgeHub task status → Kanboard column id for
    # this specific Kanboard project (since each project has its own column IDs).
    kanboard_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kanboard_column_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    modules: Mapped[list["ProductModule"]] = relationship(
        "ProductModule", back_populates="product", cascade="all, delete-orphan"
    )
    versions: Mapped[list["ProductVersion"]] = relationship(
        "ProductVersion", back_populates="product", cascade="all, delete-orphan"
    )


class ProductModule(Base, TimestampMixin):
    __tablename__ = "product_modules"
    __table_args__ = (UniqueConstraint("product_id", "name", name="uq_product_modules_product_id_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.products.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped["Product"] = relationship("Product", back_populates="modules")


class ProductVersion(Base, TimestampMixin):
    __tablename__ = "product_versions"
    __table_args__ = (
        UniqueConstraint("product_id", "version", name="uq_product_versions_product_id_version"),
        CheckConstraint(
            "status IN ('planned', 'in_development', 'in_test', 'published', 'deprecated')",
            name="ck_product_versions_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.products.id", ondelete="CASCADE"), nullable=False
    )
    # Semantic version string, e.g. "0.1.0". Stored as a plain string (not
    # split into major/minor/patch columns) — kept simple per "don't
    # gold-plate" guidance; ordering/parsing can be added later if needed.
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="planned")
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped["Product"] = relationship("Product", back_populates="versions")
    releases: Mapped[list["Release"]] = relationship(
        "Release", back_populates="product_version", cascade="all, delete-orphan"
    )


class Release(Base, TimestampMixin):
    __tablename__ = "releases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'ready', 'released', 'cancelled')",
            name="ck_releases_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.product_versions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product_version: Mapped["ProductVersion"] = relationship("ProductVersion", back_populates="releases")
