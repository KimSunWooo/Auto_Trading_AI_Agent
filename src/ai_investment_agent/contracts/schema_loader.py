"""Load the frozen JSON Schema document. Not a live registry."""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
V1_SCHEMA_NAME = "ai.trade-proposal.v1.json"


def schema_path(name: str = V1_SCHEMA_NAME) -> Path:
    return SCHEMA_DIR / name


def load_schema(name: str = V1_SCHEMA_NAME) -> dict:
    return json.loads(schema_path(name).read_text(encoding="utf-8"))
