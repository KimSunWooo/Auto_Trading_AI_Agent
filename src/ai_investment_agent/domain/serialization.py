from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ai_investment_agent.domain.errors import SerializationError

T = TypeVar("T", bound=BaseModel)


def to_json(model: BaseModel) -> str:
    return model.model_dump_json()


def from_json(model_type: type[T], raw: str) -> T:
    try:
        return model_type.model_validate_json(raw)
    except ValidationError as exc:
        raise SerializationError(str(exc)) from exc


def to_dict(model: BaseModel) -> dict:
    return model.model_dump(mode="json")
