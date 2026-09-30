"""Dated ElevenLabs Scribe price for the shared pre-send cost estimate (S12.07).

The estimate itself is the provider-neutral ``EstimateCloudTranscription`` use
case; this module only supplies the ElevenLabs entry of its price table.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from voz.application.estimate_cloud_cost import CloudPrice

PROVIDER_ID: Final = "elevenlabs"
MODEL_ID: Final = "scribe_v1"
# ponytail: dated reference constants, not a live price. Fuente: página pública
# de precios de ElevenLabs recordada el 2026-09-30, NO verificada en vivo; el
# precio real depende del plan. Cambia el número aquí (o construye otro CloudPrice).
PRICE_PER_HOUR_USD: Final = Decimal("0.40")
PRICE_DATE: Final = "2026-09-30"
PRICE_SOURCE: Final = (
    "elevenlabs.io/pricing (referencia pública, no verificada en vivo)"
)


def scribe_price(
    *,
    price_per_hour_usd: Decimal = PRICE_PER_HOUR_USD,
    date: str = PRICE_DATE,
    source: str = PRICE_SOURCE,
) -> CloudPrice:
    """Return the dated Scribe price as a per-minute ``CloudPrice``."""
    if price_per_hour_usd < 0:
        raise ValueError("price_per_hour_usd must be non-negative")
    return CloudPrice(price_per_hour_usd / 60, source, date)


ELEVENLABS_PRICES: Final = {(PROVIDER_ID, MODEL_ID): scribe_price()}
ELEVENLABS_DEFAULT_MODELS: Final = {PROVIDER_ID: MODEL_ID}

__all__ = [
    "ELEVENLABS_DEFAULT_MODELS",
    "ELEVENLABS_PRICES",
    "PRICE_DATE",
    "PRICE_PER_HOUR_USD",
    "PRICE_SOURCE",
    "scribe_price",
]
