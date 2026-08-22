"""Tests for the NewsEvent schema — the LLM output contract (SPEC §9–12)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from marketlab.core.events import (
    NEWS_EVENT_JSON_SCHEMA,
    Direction,
    EventType,
    Horizon,
    NewsEvent,
    SourceTier,
)

NOW = datetime(2026, 8, 22, 10, 3, tzinfo=UTC)


def make_event(**overrides):
    payload = {
        "source": "reuters.com",
        "source_tier": "WIRE_SERVICE",
        "publish_time": NOW,
        "event_type": "CRYPTO_REGULATION",
        "entities": ["Donald Trump", "United States", "Bitcoin"],
        "topic": "Clarity Act",
        "sentiment": 0.64,
        "crypto_direction": "POSITIVE",
        "expected_horizon": "SHORT_TERM",
        "impact_score": 0.78,
        "confidence": 0.84,
        "novelty": 0.71,
    }
    payload.update(overrides)
    return NewsEvent(**payload)


def test_valid_event_round_trips_through_json():
    event = make_event()
    restored = NewsEvent.model_validate_json(event.model_dump_json())
    assert restored.topic == "Clarity Act"
    assert restored.event_type is EventType.CRYPTO_REGULATION
    assert restored.entities == ["Donald Trump", "United States", "Bitcoin"]


def test_string_values_coerce_into_enums():
    assert make_event().crypto_direction is Direction.POSITIVE
    assert make_event().expected_horizon is Horizon.SHORT_TERM


def test_out_of_range_scores_rejected():
    with pytest.raises(ValidationError):
        make_event(sentiment=1.5)  # must be within [-1, 1]
    with pytest.raises(ValidationError):
        make_event(impact_score=-0.1)
    with pytest.raises(ValidationError):
        make_event(confidence=2.0)


def test_naive_timestamps_rejected():
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_event(publish_time=datetime(2026, 8, 22, 10, 3))


def test_json_schema_exposes_llm_contract_fields():
    properties = NEWS_EVENT_JSON_SCHEMA["properties"]
    for field in ("event_type", "entities", "topic", "sentiment",
                  "crypto_direction", "expected_horizon", "impact_score",
                  "confidence", "novelty"):
        assert field in properties
    required = set(NEWS_EVENT_JSON_SCHEMA.get("required", []))
    assert {"event_type", "impact_score", "confidence"} <= required


def test_source_tier_weights_ordered_by_reliability():
    order = [
        SourceTier.OFFICIAL_GOVERNMENT,
        SourceTier.WIRE_SERVICE,
        SourceTier.CRYPTO_MEDIA,
        SourceTier.SOCIAL_MEDIA,
        SourceTier.UNKNOWN,
    ]
    weights = [tier.weight for tier in order]
    assert weights == sorted(weights, reverse=True)


def test_effective_impact_discounts_confidence_and_source():
    event = make_event()
    expected = 0.78 * 0.84 * SourceTier.WIRE_SERVICE.weight
    assert event.effective_impact == pytest.approx(expected)
