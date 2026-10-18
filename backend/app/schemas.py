"""Request bodies (API_CONTRACT.md). Unknown fields are rejected.

There is intentionally no field for a user id, role, permission grant,
destination URL, replacement payload, unredact or include_<field> option.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, field_validator

Identifier = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9_\-]{1,64}$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionBody(_Strict):
    account_id: Identifier


class PreviewBody(_Strict):
    dataset_id: Identifier
    purpose: Identifier
    destination: Identifier  # a configured identifier, never a URL


class ReviewBody(_Strict):
    expected_review_revision: Annotated[StrictInt, Field(ge=1)]
    hide_message_indices: Annotated[list[StrictInt], Field(max_length=10_000)]


class SendBody(_Strict):
    approve: StrictBool
    expected_review_revision: Annotated[StrictInt, Field(ge=1)]
    preview_hash: Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]

    @field_validator("approve")
    @classmethod
    def _must_approve(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("approve must be true")
        return value
