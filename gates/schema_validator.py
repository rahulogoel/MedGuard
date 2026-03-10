"""
Gate 1 — Schema Validation using Pydantic.

Validates every record against the Canonical Schema.  Records that fail
are flagged for the Fixer Agent.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator


class CanonicalRecord(BaseModel):
    """The Canonical Schema that every record must match."""

    record_id: str
    patient_name: str
    date_of_visit: str          # Will be normalised to ISO 8601 later
    diagnosis_code: str         # ICD-10
    status: str
    notes: Optional[str] = None

    @field_validator("record_id")
    @classmethod
    def record_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("record_id must be a non-empty string")
        return v.strip()

    @field_validator("patient_name")
    @classmethod
    def patient_name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("patient_name must be a non-empty string")
        return v.strip()

    @field_validator("diagnosis_code")
    @classmethod
    def diagnosis_code_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("diagnosis_code must be a non-empty string")
        return v.strip()

    @field_validator("status")
    @classmethod
    def status_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("status must be a non-empty string")
        return v.strip()


def validate(record: dict) -> tuple[bool, CanonicalRecord | None, list[str]]:
    """
    Attempt to validate a raw record against the Canonical Schema.

    Returns:
        (is_valid, parsed_record_or_None, list_of_errors)
    """
    try:
        parsed = CanonicalRecord(**record)
        return True, parsed, []
    except Exception as exc:
        errors = []
        if hasattr(exc, "errors"):
            for err in exc.errors():              # type: ignore[union-attr]
                loc = " -> ".join(str(l) for l in err["loc"])
                errors.append(f"{loc}: {err['msg']}")
        else:
            errors.append(str(exc))
        return False, None, errors
