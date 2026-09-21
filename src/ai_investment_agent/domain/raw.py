from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from ai_investment_agent.domain.base import DomainModel


def compute_raw_checksum(
    source: str,
    raw_payload: dict[str, Any] | None,
    raw_text: str | None,
) -> str:
    """Fingerprint of source + body. sourceId is excluded so republishes collide."""
    payload_part = (
        json.dumps(raw_payload, sort_keys=True, default=str) if raw_payload is not None else ""
    )
    text_part = raw_text or ""
    material = "\0".join([source, payload_part, text_part])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class RawRecord(DomainModel):
    source: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    collected_at: datetime
    checksum: str = Field(min_length=1)
    raw_payload: dict[str, Any] | None = None
    raw_text: str | None = None
    published_at: datetime | None = None

    @model_validator(mode="after")
    def check_body(self) -> RawRecord:
        if self.raw_payload is None and self.raw_text is None:
            raise ValueError("rawPayload or rawText is required")
        if self.collected_at.tzinfo is None:
            raise ValueError("collectedAt must be timezone-aware")
        if self.published_at is not None and self.published_at.tzinfo is None:
            raise ValueError("publishedAt must be timezone-aware")
        return self
