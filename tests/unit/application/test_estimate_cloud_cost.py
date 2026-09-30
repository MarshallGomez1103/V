"""Pure cost estimate and its use case (no provider is contacted)."""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from voz.application.estimate_cloud_cost import (
    CloudPrice,
    EstimateCloudTranscription,
    EstimateError,
    EstimateFailureCode,
    estimate_cost,
)
from voz.domain.entities.media_asset import MediaAsset

PRICE = CloudPrice(Decimal("0.006"), "docs (no verificado)", "2026-09-30")


def test_estimate_is_exact_for_whole_minutes() -> None:
    estimate = estimate_cost(600_000, PRICE)
    assert (estimate.minutes, estimate.usd) == (10.0, 0.06)
    assert (estimate.price_source, estimate.price_date) == (PRICE.source, PRICE.date)


def test_estimate_rounds_up_so_it_never_undershoots() -> None:
    estimate = estimate_cost(1, PRICE)
    assert estimate.minutes == 0.001
    assert estimate.usd == 0.0001


@pytest.mark.parametrize("duration", [0, -1])
def test_non_positive_duration_is_rejected(duration: int) -> None:
    with pytest.raises(ValueError, match="duration_ms"):
        estimate_cost(duration, PRICE)


class _Assets:
    def __init__(self, asset: MediaAsset | None) -> None:
        self.asset = asset

    def get(self, media_asset_id: UUID) -> MediaAsset | None:
        return self.asset


def _asset(duration_ms: int | None) -> MediaAsset:
    return MediaAsset(uuid4(), "0" * 64, "clase.wav", 10, duration_ms=duration_ms)


def _use_case(asset: MediaAsset | None) -> EstimateCloudTranscription:
    return EstimateCloudTranscription(
        _Assets(asset),  # type: ignore[arg-type]
        {("openai", "whisper-1"): PRICE},
        {"openai": "whisper-1"},
    )


def test_use_case_prices_the_asset_duration() -> None:
    result = _use_case(_asset(120_000)).execute("openai", uuid4())
    assert result.usd == 0.012


@pytest.mark.parametrize(
    ("asset", "provider", "code"),
    [
        (None, "openai", EstimateFailureCode.MEDIA_NOT_FOUND),
        (_asset(None), "openai", EstimateFailureCode.DURATION_UNKNOWN),
        (_asset(1_000), "other", EstimateFailureCode.PROVIDER_NOT_FOUND),
    ],
)
def test_use_case_failures_are_typed(
    asset: MediaAsset | None, provider: str, code: EstimateFailureCode
) -> None:
    with pytest.raises(EstimateError) as raised:
        _use_case(asset).execute(provider, uuid4())
    assert raised.value.code is code
