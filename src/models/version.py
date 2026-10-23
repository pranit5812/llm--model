"""Version management models for the ICMR Standard Treatment Workflow (STW) Platform.

Supports deterministic document versioning, content hashing, supersession tracking,
and precedence resolution in compliance with clinical AI governance.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class VersionPrecedence(str, Enum):
    """Clinical version precedence classification."""
    CURRENT = "CURRENT"
    SUPERSEDED = "SUPERSEDED"
    VERSION_PRECEDENCE_UNKNOWN = "VERSION_PRECEDENCE_UNKNOWN"


class DocumentVersion(BaseModel):
    """Represents a specific, immutable version snapshot of an official ICMR STW document."""
    model_config = ConfigDict(protected_namespaces=())

    document_id: str = Field(
        ...,
        description="Canonical STW document ID, e.g. 'ICMR-CARD-006' or 'ICMR-NEUR-001'",
        min_length=3,
    )
    specialty: str = Field(
        default="General",
        description="Clinical specialty, e.g. 'Cardiology', 'Neurology'",
    )
    condition: str = Field(
        default="Unknown",
        description="Target medical condition or syndrome",
    )
    version_id: str = Field(
        default="v1.0",
        description="Semantic version string, e.g. 'v1.0', 'v1.1'",
    )

    version_label: str = Field(
        default="Official Edition 2019",
        description="Descriptive human-readable version label, e.g. 'Volume 1 (2019)' or 'Updated 2022'",
    )
    source_url: str = Field(
        ...,
        description="Authoritative ICMR portal URL for this version",
    )
    download_date: str = Field(
        ...,
        description="ISO 8601 UTC date/time when this version was downloaded",
    )
    content_hash: str = Field(
        ...,
        description="SHA-256 checksum of the source PDF file",
        min_length=64,
        max_length=64,
    )
    is_current: bool = Field(
        default=True,
        description="Whether this version is explicitly identified as active/current in the official source catalogue",
    )
    supersedes: Optional[str] = Field(
        default=None,
        description="version_id of the previous version superseded by this document, if known",
    )
    review_status: str = Field(
        default="needs_review",
        description="Clinical review status for this version: 'approved', 'needs_review', 'rejected'",
    )
    version_precedence: VersionPrecedence = Field(
        default=VersionPrecedence.CURRENT,
        description="Precedence status: CURRENT, SUPERSEDED, or VERSION_PRECEDENCE_UNKNOWN",
    )
