from __future__ import annotations


class DomainError(Exception):
    """Base class for recoverable domain rule violations."""


class InvalidDecisionError(DomainError):
    pass


class SerializationError(DomainError):
    pass
