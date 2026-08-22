"""NewsEvent schema — the fixed contract between LLM and quant system (SPEC §9–12).

Design rules enforced here:
* The LLM must emit exactly this JSON shape (see NEWS_EVENT_JSON_SCHEMA);
* Sentiment alone is never enough — event type, direction, horizon, novelty
  and source reliability travel with every event;
* Source reliability downweights weak sources via ``effective_impact``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

# Source reliability weights (SPEC §12): official wire > major news > social > unknown
_TIER_WEIGHTS: dict[str, float] = {
    "OFFICIAL_GOVERNMENT": 1.00,
    "CENTRAL_BANK": 0.95,
    "REGULATOR": 0.95,
    "WIRE_SERVICE": 0.85,
    "MAJOR_NEWS": 0.75,
    "CRYPTO_MEDIA": 0.55,
    "SOCIAL_MEDIA": 0.35,
    "UNKNOWN": 0.20,
}


class EventType(StrEnum):
    """Event taxonomy (SPEC §10). Sentiment alone cannot express these."""

    MONETARY_POLICY = "MONETARY_POLICY"
    CRYPTO_REGULATION = "CRYPTO_REGULATION"
    TRADE_POLICY = "TRADE_POLICY"
    ETF = "ETF"
    GEOPOLITICS = "GEOPOLITICS"
    SEC = "SEC"
    CFTC = "CFTC"
    EXCHANGE = "EXCHANGE"
    SECURITY_BREACH = "SECURITY_BREACH"
    LIQUIDITY = "LIQUIDITY"
    MACRO = "MACRO"
    OTHER = "OTHER"


class Direction(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


class Horizon(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    SHORT_TERM = "SHORT_TERM"
    MEDIUM_TERM = "MEDIUM_TERM"
    LONG_TERM = "LONG_TERM"


class SourceTier(StrEnum):
    OFFICIAL_GOVERNMENT = "OFFICIAL_GOVERNMENT"
    CENTRAL_BANK = "CENTRAL_BANK"
    REGULATOR = "REGULATOR"
    WIRE_SERVICE = "WIRE_SERVICE"
    MAJOR_NEWS = "MAJOR_NEWS"
    CRYPTO_MEDIA = "CRYPTO_MEDIA"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    UNKNOWN = "UNKNOWN"

    @property
    def weight(self) -> float:
        """Reliability weight used to discount impact from weak sources."""
        return _TIER_WEIGHTS[self.value]


class NewsEvent(BaseModel):
    """Canonical structured market event.

    LLM-produced fields mirror SPEC §9 exactly; provenance fields come from
    the collector (SPEC §12). ``id`` enables dedup / clustering later (§13).
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)

    # --- provenance (collector-provided) ---
    source: str
    source_tier: SourceTier
    publish_time: datetime
    receive_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    url: str | None = None
    author: str | None = None
    revision_time: datetime | None = None
    title: str | None = None

    # --- LLM structured output (SPEC §9) ---
    event_type: EventType
    entities: list[str] = Field(default_factory=list)
    topic: str
    sentiment: float = Field(ge=-1.0, le=1.0)
    crypto_direction: Direction
    expected_horizon: Horizon
    impact_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    novelty: float = Field(ge=0.0, le=1.0)

    @field_validator("publish_time", "receive_time", "revision_time")
    @classmethod
    def _ensure_tz(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC recommended)")
        return value

    @property
    def effective_impact(self) -> float:
        """Impact discounted by model confidence and source reliability."""
        return self.impact_score * self.confidence * self.source_tier.weight


NEWS_EVENT_JSON_SCHEMA: dict = NewsEvent.model_json_schema()
"""Fixed JSON contract handed to the LLM (SPEC §9)."""
