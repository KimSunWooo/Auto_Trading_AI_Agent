"""Deterministic context fingerprint. No raw document bodies are hashed."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Iterable

from ai_investment_agent.domain.enums import DataMode
from ai_investment_agent.domain.versions import FEATURE_VERSION, MODEL_VERSION, POLICY_VERSION


def context_fingerprint(
    *,
    ticker: str,
    analysis_as_of: datetime,
    event_ids: Iterable[str],
    last_price: object | None,
    feature_version: str = FEATURE_VERSION,
    model_version: str = MODEL_VERSION,
    policy_version: str = POLICY_VERSION,
    data_mode: DataMode = DataMode.FIXTURE,
) -> str:
    payload = {
        "ticker": ticker,
        "analysisAsOf": analysis_as_of.isoformat(),
        "eventIds": sorted(event_ids),
        "lastPrice": None if last_price is None else str(last_price),
        "featureVersion": feature_version,
        "modelVersion": model_version,
        "policyVersion": policy_version,
        "dataMode": data_mode.value,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"cfp_{digest[:32]}"
