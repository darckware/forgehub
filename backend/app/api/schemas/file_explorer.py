"""Workspace Explorer request/response schemas -- see
api/routes/file_explorer.py. Every path here is an absolute HOST path."""

from pydantic import BaseModel, Field


class ExplorerEntry(BaseModel):
    name: str
    path: str
    type: str  # "file" | "dir"
    size: int | None = None
    modified: float | None = None
    is_symlink: bool = False


class ExplorerListing(BaseModel):
    path: str
    parent: str | None
    entries: list[ExplorerEntry]


class ExplorerSearchResult(BaseModel):
    path: str
    query: str
    entries: list[ExplorerEntry]
    truncated: bool


class ExplorerFileContent(BaseModel):
    path: str
    content: str


class ExplorerContentUpdate(BaseModel):
    content: str


class ExplorerPath(BaseModel):
    path: str = Field(min_length=1)


class ExplorerMove(BaseModel):
    path: str = Field(min_length=1)
    new_path: str = Field(min_length=1)


class ExplorerZipRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=1000)
    name: str = "download.zip"
