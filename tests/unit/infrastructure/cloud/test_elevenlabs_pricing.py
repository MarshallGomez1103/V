"""S12.07: the dated Scribe price plugs into the shared estimate."""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from voz.application.estimate_cloud_cost import (
    EstimateCloudTranscription,
    EstimateError,
    estimate_cost,
)
from voz.domain.entities.media_asset import MediaAsset
from voz.infrastructure.cloud.elevenlabs_pricing import (
    ELEVENLABS_DEFAULT_MODELS,
    ELEVENLABS_PRICES,
    PRICE_DATE,
    scribe_price,
)


class _Assets:
    def __init__(self, asset: MediaAsset) -> None:
        self.asset = asset

    def get(self, media_asset_id: UUID) -> MediaAsset | None:
        return self.asset if media_asset_id == self.asset.id else None

    def add(self, media_asset: MediaAsset) -> None:
        raise AssertionError

    def save(self, media_asset: MediaAsset) -> None:
        raise AssertionError

    def list_by_project(self, project_id: UUID) -> Sequence[MediaAsset]:
        raise AssertionError


def _asset(duration_ms: int | None) -> MediaAsset:
    return MediaAsset(
        project_id=uuid4(),
        content_sha256="a" * 64,
        display_name="clase.mp3",
        size_bytes=10,
        duration_ms=duration_ms,
    )


def test_one_hour_costs_the_dated_hourly_price() -> None:
    estimate = estimate_cost(3_600_000, scribe_price())

    assert estimate.minutes == 60.0
    assert estimate.usd == 0.4
    assert estimate.price_date == PRICE_DATE
    assert "no verificada" in estimate.price_source


def test_price_per_hour_is_configurable() -> None:
    price = scribe_price(price_per_hour_usd=Decimal("1.20"), date="x", source="s")

    estimate = estimate_cost(1_800_000, price)

    assert (estimate.usd, estimate.price_date, estimate.price_source) == (0.6, "x", "s")


def test_negative_price_is_rejected() -> None:
    with pytest.raises(ValueError, match="price_per_hour_usd"):
        scribe_price(price_per_hour_usd=Decimal(-1))


def test_shared_use_case_prices_an_elevenlabs_asset_with_the_default_model() -> None:
    asset = _asset(90_000)
    use_case = EstimateCloudTranscription(
        _Assets(asset), ELEVENLABS_PRICES, ELEVENLABS_DEFAULT_MODELS
    )

    estimate = use_case.execute("elevenlabs", asset.id)

    assert estimate.minutes == 1.5
    assert estimate.usd == 0.01


def test_unknown_model_and_missing_duration_fail_with_stable_codes() -> None:
    asset = _asset(None)
    use_case = EstimateCloudTranscription(
        _Assets(asset), ELEVENLABS_PRICES, ELEVENLABS_DEFAULT_MODELS
    )

    with pytest.raises(EstimateError) as no_duration:
        use_case.execute("elevenlabs", asset.id)
    with pytest.raises(EstimateError) as no_model:
        use_case.execute("elevenlabs", asset.id, "other")

    assert no_duration.value.code == "media_duration_unknown"
    assert no_model.value.code == "provider_not_found"
