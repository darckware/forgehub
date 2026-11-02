import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from pydantic import ValidationError
from fastapi import HTTPException

from app.api.schemas.terminal_metadata import TerminalMetadataUpdate


def test_terminal_metadata_validates_names_and_note_size():
    assert TerminalMetadataUpdate(label="  Codex  ").label == "Codex"
    with pytest.raises(ValidationError):
        TerminalMetadataUpdate(label="  ")
    with pytest.raises(ValidationError):
        TerminalMetadataUpdate(notes="x" * 20001)


@pytest.mark.asyncio
async def test_stale_notes_are_rejected_without_committing():
    from app.api.routes.terminal import update_terminal_metadata

    db = MagicMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    db.commit = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await update_terminal_metadata(uuid.uuid4(), TerminalMetadataUpdate(notes="new", expected_notes="old"), user=None, db=db)
    assert exc.value.status_code == 409
    db.commit.assert_not_awaited()
