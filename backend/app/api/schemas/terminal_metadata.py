from pydantic import BaseModel, Field, field_validator


class TerminalMetadataUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=20000)
    expected_notes: str | None = Field(default=None, max_length=20000)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Label must not be empty")
        return value
