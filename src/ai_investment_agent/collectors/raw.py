from __future__ import annotations

from ai_investment_agent.domain.enums import RawPutResult
from ai_investment_agent.domain.raw import RawRecord, compute_raw_checksum


class InMemoryRawStore:
    """Deduplicating raw record store. No Redis, Kafka, or shared auto-trading DB."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], RawRecord] = {}
        self._by_checksum: dict[str, RawRecord] = {}

    def put(self, record: RawRecord) -> RawPutResult:
        checksum = record.checksum or compute_raw_checksum(
            record.source, record.raw_payload, record.raw_text
        )
        if checksum != record.checksum:
            record = record.model_copy(update={"checksum": checksum})
        key = (record.source, record.source_id)
        if key in self._by_key or checksum in self._by_checksum:
            return RawPutResult.DUPLICATE
        self._by_key[key] = record
        self._by_checksum[checksum] = record
        return RawPutResult.STORED

    def get(self, source: str, source_id: str) -> RawRecord | None:
        return self._by_key.get((source, source_id))

    def get_by_checksum(self, checksum: str) -> RawRecord | None:
        return self._by_checksum.get(checksum)

    def __len__(self) -> int:
        return len(self._by_key)
