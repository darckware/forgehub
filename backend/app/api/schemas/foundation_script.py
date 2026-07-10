"""Pydantic schemas for the Foundation page's Scripts registry."""
from datetime import datetime

from pydantic import BaseModel, Field


class FoundationScriptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    path: str | None = Field(default=None, max_length=512)
    description: str | None = None
    doc_path: str | None = Field(default=None, max_length=512)


class FoundationScriptUpdate(BaseModel):
    path: str | None = Field(default=None, max_length=512)
    description: str | None = None
    doc_path: str | None = Field(default=None, max_length=512)


class FoundationScriptOut(BaseModel):
    id: str
    name: str
    path: str | None
    description: str | None
    doc_path: str | None
    source: str
    created_at: datetime
    updated_at: datetime


class FoundationScriptSyncOut(BaseModel):
    added: int
    already_registered: int
    scanned_docs: int
    discovered: list[str]


class FoundationScriptContentOut(BaseModel):
    content: str
