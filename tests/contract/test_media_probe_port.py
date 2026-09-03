"""Contract tests for media inspection adapters."""

from pathlib import Path

from voz.application.ports.media_probe import (
    MediaProbePort,
    MediaProbeResult,
    MediaStreamKind,
    ProbedMediaStream,
)


class _ContractProbe:
    def probe(self, source: Path) -> MediaProbeResult:
        del source
        return MediaProbeResult(
            format_names=("wav",),
            streams=(
                ProbedMediaStream(
                    index=0,
                    kind=MediaStreamKind.AUDIO,
                    codec_name="pcm_s16le",
                    is_decodable=True,
                    sample_rate_hz=16_000,
                    channels=1,
                ),
            ),
            duration_ms=1_000,
        )


def _accept_media_probe(probe: MediaProbePort) -> MediaProbePort:
    return probe


def test_port_is_structural_and_returns_path_free_metadata() -> None:
    adapter = _ContractProbe()
    probe = _accept_media_probe(adapter)

    result = probe.probe(Path("/private/recordings/class.wav"))

    assert isinstance(adapter, MediaProbePort)
    assert result.format_names == ("wav",)
    assert result.duration_ms == 1_000
    assert not hasattr(result, "path")
    assert not hasattr(result, "filename")


def test_result_requires_at_least_one_decodable_audio_stream() -> None:
    stream = ProbedMediaStream(
        index=0,
        kind=MediaStreamKind.VIDEO,
        codec_name="h264",
        is_decodable=True,
    )

    try:
        MediaProbeResult(format_names=("mov",), streams=(stream,))
    except ValueError as error:
        assert str(error) == "a probe result requires decodable audio"
    else:
        raise AssertionError("silent video must not satisfy the probe contract")
