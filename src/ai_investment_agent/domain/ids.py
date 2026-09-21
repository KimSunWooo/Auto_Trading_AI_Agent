from __future__ import annotations

from uuid import uuid4


def new_decision_id() -> str:
    return f"dec_{uuid4().hex}"


def new_journal_id() -> str:
    return f"jnl_{uuid4().hex}"


def new_event_id() -> str:
    return f"evt_{uuid4().hex}"


def new_record_id(prefix: str = "rec") -> str:
    return f"{prefix}_{uuid4().hex}"


def new_cluster_id() -> str:
    return f"ecl_{uuid4().hex}"


def is_decision_id(value: str) -> bool:
    return value.startswith("dec_") and len(value) == 36
