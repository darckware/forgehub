"""Pydantic schemas for the Product domain (products, product_modules,
product_versions, releases).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.product import PRODUCT_VERSION_STATUSES, RELEASE_STATUSES

# ---------------------------------------------------------------------------
# ProductModule
# ---------------------------------------------------------------------------


class ProductModuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ProductModuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class ProductModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ProductVersion
# ---------------------------------------------------------------------------


class ProductVersionCreate(BaseModel):
    version: str = Field(min_length=1, max_length=50)
    status: str = Field(default="planned")
    release_notes: str | None = None


class ProductVersionUpdate(BaseModel):
    """Fields allowed to be updated on a ProductVersion.

    Business rule 6.1.4: published versions cannot be mutated directly.
    The route enforces that any update on a version whose current status
    is "published" is rejected (422), regardless of which fields are sent
    here. Transitioning *into* "published" is allowed.
    """

    version: str | None = Field(default=None, min_length=1, max_length=50)
    status: str | None = None
    release_notes: str | None = None


class ProductVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    version: str
    status: str
    release_notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Product (primary entity)
# ---------------------------------------------------------------------------


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: str = Field(default="active")
    # One URL per environment. `application_url` is the production address
    # (historical name, kept -- see the model's comment); `application_url_dev`
    # is the development one.
    application_url: str | None = Field(default=None, max_length=2048, pattern=r"^https?://")
    application_url_dev: str | None = Field(default=None, max_length=2048, pattern=r"^https?://")
    # Business rule 6.1.3: every product must have at least one version.
    # Optional here only insofar as a default "0.1.0 / planned" version is
    # created automatically when the caller omits it — the product is
    # never persisted without at least one version either way.
    initial_version: ProductVersionCreate | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = None
    application_url: str | None = Field(default=None, max_length=2048, pattern=r"^https?://")
    application_url_dev: str | None = Field(default=None, max_length=2048, pattern=r"^https?://")


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    status: str
    application_url: str | None = None
    application_url_dev: str | None = None
    created_at: datetime
    updated_at: datetime


class ProductWithVersionsOut(ProductOut):
    versions: list[ProductVersionOut] = []
    modules: list[ProductModuleOut] = []


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------


class ReleaseCreate(BaseModel):
    product_version_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    status: str = Field(default="draft")
    notes: str | None = None


class ReleaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    notes: str | None = None


class ReleaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_version_id: uuid.UUID
    name: str
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


VALID_PRODUCT_VERSION_STATUSES = set(PRODUCT_VERSION_STATUSES)
VALID_RELEASE_STATUSES = set(RELEASE_STATUSES)
