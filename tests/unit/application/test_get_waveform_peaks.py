"""GetWaveformPeaks validates input and delegates decoding to its port."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from voz.application.ports.waveform import (
    PeakSeries,
    WaveformError,
    WaveformFailureCode,
)
from voz.application.waveform_peaks import GetWaveformPeaks
from voz.domain.entities.media_asset import MediaAsset


class _Assets:
    def __init__(self, asset: MediaAsset | None) -> None:
        self._asset = asset

    def get(self, media_asset_id: UUID) -> MediaAsset | None:
        return self._asset if self._asset and self._asset.id == media_asset_id else None


class _Provider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def peaks(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
        content_sha256: str,
        buckets: int,
    ) -> PeakSeries:
        self.calls.append({"sha": content_sha256, "buckets": buckets})
        return PeakSeries(duration_ms=999, peaks=((-1.0, 1.0),) * buckets)


def _asset(duration_ms: int | None) -> MediaAsset:
    return MediaAsset(
        uuid4(), "a" * 64, "clase.wav", 10, duration_ms=duration_ms, media_type=None
    )


def _use_case(asset: MediaAsset | None) -> tuple[GetWaveformPeaks, _Provider]:
    provider = _Provider()
    return GetWaveformPeaks(_Assets(asset), provider), provider  # type: ignore[arg-type]


def test_returns_peaks_with_the_probed_duration() -> None:
    asset = _asset(1234)
    use_case, provider = _use_case(asset)

    result = use_case.execute(asset.id, 100)

    assert (result.media_asset_id, result.duration_ms, result.buckets) == (
        asset.id,
        1234,
        100,
    )
    assert len(result.peaks) == 100
    assert provider.calls == [{"sha": "a" * 64, "buckets": 100}]


def test_falls_back_to_decoded_duration_when_probe_is_missing() -> None:
    asset = _asset(None)
    use_case, _ = _use_case(asset)

    assert use_case.execute(asset.id, 100).duration_ms == 999


@pytest.mark.parametrize("buckets", [-1, 0, 99, 20_001])
def test_out_of_range_buckets_are_rejected_before_any_work(buckets: int) -> None:
    asset = _asset(1000)
    use_case, provider = _use_case(asset)

    with pytest.raises(WaveformError) as caught:
        use_case.execute(asset.id, buckets)

    assert caught.value.code is WaveformFailureCode.BUCKETS_INVALID
    assert provider.calls == []


def test_bucket_range_edges_are_accepted() -> None:
    asset = _asset(1000)
    use_case, _ = _use_case(asset)

    assert use_case.execute(asset.id, 100).buckets == 100
    assert use_case.execute(asset.id, 20_000).buckets == 20_000


def test_unknown_asset_is_reported() -> None:
    use_case, provider = _use_case(None)

    with pytest.raises(WaveformError) as caught:
        use_case.execute(uuid4(), 100)

    assert caught.value.code is WaveformFailureCode.MEDIA_ASSET_NOT_FOUND
    assert provider.calls == []
