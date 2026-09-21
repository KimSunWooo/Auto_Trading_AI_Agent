from datetime import datetime, timezone

from ai_investment_agent.collectors.raw import InMemoryRawStore
from ai_investment_agent.domain.enums import RawPutResult
from ai_investment_agent.domain.raw import RawRecord, compute_raw_checksum

NOW = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def _raw(
    *,
    source_id: str,
    payload: dict | None = None,
    text: str | None = None,
    source: str = "fixture-news",
) -> RawRecord:
    body = payload if payload is not None or text is not None else {"headline": "fixture"}
    checksum = compute_raw_checksum(source, body if text is None else None, text)
    return RawRecord(
        source=source,
        source_id=source_id,
        raw_payload=body if text is None else payload,
        raw_text=text,
        published_at=NOW,
        collected_at=NOW,
        checksum=checksum,
    )


def test_duplicate_source_and_source_id_is_rejected():
    store = InMemoryRawStore()
    first = _raw(source_id="n-1", payload={"headline": "one"})
    second = _raw(source_id="n-1", payload={"headline": "one-again"})
    # same source+id, different body still collides on the identity key
    second = second.model_copy(
        update={"checksum": compute_raw_checksum(second.source, second.raw_payload, second.raw_text)}
    )

    assert store.put(first) is RawPutResult.STORED
    assert store.put(second) is RawPutResult.DUPLICATE
    assert len(store) == 1
    assert store.get("fixture-news", "n-1") == first


def test_duplicate_checksum_is_rejected_even_with_new_source_id():
    store = InMemoryRawStore()
    payload = {"headline": "same wire body"}
    first = _raw(source_id="n-1", payload=payload)
    second = _raw(source_id="n-2", payload=payload)

    assert first.checksum == second.checksum
    assert store.put(first) is RawPutResult.STORED
    assert store.put(second) is RawPutResult.DUPLICATE
    assert len(store) == 1
    assert store.get("fixture-news", "n-2") is None
    assert store.get_by_checksum(first.checksum) == first


def test_distinct_payloads_are_stored():
    store = InMemoryRawStore()
    a = _raw(source_id="n-1", payload={"headline": "a"})
    b = _raw(source_id="n-2", payload={"headline": "b"})
    assert store.put(a) is RawPutResult.STORED
    assert store.put(b) is RawPutResult.STORED
    assert len(store) == 2
