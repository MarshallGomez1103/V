"""Pre-flight cost estimate for cloud transcription (nothing is sent)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum
from uuid import UUID

from voz.application.ports.repositories import MediaAssetRepository

_MS_PER_MINUTE = Decimal(60_000)
_USD_STEP = Decimal("0.0001")
_MINUTE_STEP = Decimal("0.001")


@dataclass(frozen=True, slots=True)
class CloudPrice:
    """Dated per-minute price; ``source`` says where the number came from."""

    usd_per_minute: Decimal
    source: str
    date: str


@dataclass(frozen=True, slots=True)
class CostEstimate:
    minutes: float
    usd: float
    price_source: str
    price_date: str


class EstimateFailureCode(StrEnum):
    PROVIDER_NOT_FOUND = "provider_not_found"
    MEDIA_NOT_FOUND = "media_not_found"
    DURATION_UNKNOWN = "media_duration_unknown"


class EstimateError(LookupError):
    def __init__(self, code: EstimateFailureCode, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


def estimate_cost(duration_ms: int, price: CloudPrice) -> CostEstimate:
    """Pure: minutes and USD, rounded up so the estimate never undershoots."""
    if type(duration_ms) is not int or duration_ms <= 0:
        raise ValueError("duration_ms must be a positive integer")
    minutes = Decimal(duration_ms) / _MS_PER_MINUTE
    return CostEstimate(
        minutes=float(minutes.quantize(_MINUTE_STEP, rounding=ROUND_CEILING)),
        usd=float(
            (minutes * price.usd_per_minute).quantize(_USD_STEP, rounding=ROUND_CEILING)
        ),
        price_source=price.source,
        price_date=price.date,
    )


@dataclass(frozen=True, slots=True)
class EstimateCloudTranscription:
    """Look up a media asset and price it; prices are keyed ``(provider, model)``."""

    media_assets: MediaAssetRepository
    prices: Mapping[tuple[str, str], CloudPrice]
    default_models: Mapping[str, str]

    def execute(
        self, provider_id: str, media_asset_id: UUID, model_id: str | None = None
    ) -> CostEstimate:
        model = model_id or self.default_models.get(provider_id)
        price = self.prices.get((provider_id, model or ""))
        if price is None:
            raise EstimateError(
                EstimateFailureCode.PROVIDER_NOT_FOUND,
                "No price is known for that cloud provider and model.",
            )
        asset = self.media_assets.get(media_asset_id)
        if asset is None:
            raise EstimateError(
                EstimateFailureCode.MEDIA_NOT_FOUND, "The media asset was not found."
            )
        if asset.duration_ms is None:
            raise EstimateError(
                EstimateFailureCode.DURATION_UNKNOWN,
                "The media duration is unknown, so the cost cannot be estimated.",
            )
        return estimate_cost(asset.duration_ms, price)


__all__ = [
    "CloudPrice",
    "CostEstimate",
    "EstimateCloudTranscription",
    "EstimateError",
    "EstimateFailureCode",
    "estimate_cost",
]
