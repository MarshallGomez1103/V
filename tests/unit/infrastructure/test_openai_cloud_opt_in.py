"""S11.13: cloud is listed but never recommended, selected or used implicitly."""

from io import BytesIO
from pathlib import Path

import pytest

from voz.application.get_transcription_options import (
    BlockingReason,
    GetTranscriptionOptions,
)
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionResult,
)
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
)
from voz.application.transcription_provider_registry import (
    TranscriptionProviderRegistry,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.cloud.catalog import (
    CloudRuntimeProbe,
    CloudTranscriptionCatalog,
    CompositeCatalog,
    RoutingRuntimeProbe,
)
from voz.infrastructure.cloud.openai_fake import FakeOpenAITransport
from voz.infrastructure.cloud.openai_limits import openai_descriptors
from voz.infrastructure.cloud.openai_transcription import OpenAITranscriptionProvider
from voz.infrastructure.secrets import ProviderSecrets

KEY = "sk-opt-in-key"
LOCAL = ModelDescriptor(
    provider_id="local-asr",
    model_id="tiny",
    display_name="Local tiny",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/tiny",
    revision="a" * 40,
)


class _LocalCatalog:
    def list_models(self) -> tuple[ModelRegistration, ...]:
        return (ModelRegistration(LOCAL, InstallationStatus.REGISTERED, True),)


class _LocalProbe:
    def probe(self, provider_id: str) -> RuntimeAvailability:
        return RuntimeAvailability(
            provider_id == "local-asr",
            capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
        )


def _query(secrets: ProviderSecrets) -> GetTranscriptionOptions:
    descriptors = openai_descriptors()
    probe = CloudRuntimeProbe(secrets, descriptors)
    return GetTranscriptionOptions(
        CompositeCatalog((_LocalCatalog(), CloudTranscriptionCatalog(descriptors))),
        RoutingRuntimeProbe(_LocalProbe(), {pid: probe for pid in probe.provider_ids}),
    )


def _secrets(tmp_path: Path, **environ: str) -> ProviderSecrets:
    return ProviderSecrets(tmp_path / "voz", environ=environ)


def test_without_a_key_cloud_options_exist_but_are_unavailable(tmp_path: Path) -> None:
    options = _query(_secrets(tmp_path)).execute().options
    cloud = [item for item in options if item.cloud]
    assert {item.model_id for item in cloud} == {
        "whisper-1",
        "gpt-4o-transcribe-diarize",
    }
    for item in cloud:
        assert item.can_start is False
        assert item.runtime_available is False
        assert BlockingReason.RUNTIME_UNAVAILABLE in item.blocking_reasons
        assert item.recommendation is None
    local = next(item for item in options if not item.cloud)
    assert local.cloud is False
    assert local.provider_id == "local-asr"


def test_with_a_key_cloud_can_start_but_is_never_recommended(tmp_path: Path) -> None:
    options = _query(_secrets(tmp_path, OPENAI_API_KEY=KEY)).execute().options
    cloud = [item for item in options if item.cloud]
    assert all(item.can_start for item in cloud)
    assert all(item.recommendation is None for item in cloud)
    assert all(item.blocking_reasons == () for item in cloud)
    assert all(item.provider_id == "openai" for item in cloud)
    diarized = next(i for i in cloud if i.model_id == "gpt-4o-transcribe-diarize")
    assert ModelCapability.DIARIZATION in diarized.capabilities
    assert all(item.execution is None and item.profile is None for item in cloud)


def test_local_option_is_unchanged_by_cloud_flag(tmp_path: Path) -> None:
    local = [i for i in _query(_secrets(tmp_path)).execute().options if not i.cloud]
    assert [i.provider_id for i in local] == ["local-asr"]
    assert local[0].cloud is False


def test_listing_and_registering_with_a_key_makes_zero_requests(tmp_path: Path) -> None:
    secrets = _secrets(tmp_path, OPENAI_API_KEY=KEY)
    transport = FakeOpenAITransport()
    provider = OpenAITranscriptionProvider(secrets=secrets, transport=transport)
    registry = TranscriptionProviderRegistry([provider])
    _query(secrets).execute()
    registry.get("openai")
    registry.list_all()
    assert transport.calls == 0


def test_only_an_explicit_openai_selection_sends_audio(tmp_path: Path) -> None:
    secrets = _secrets(tmp_path, OPENAI_API_KEY=KEY)
    transport = FakeOpenAITransport()
    openai = OpenAITranscriptionProvider(secrets=secrets, transport=transport)

    class _FailingLocal:
        provider_id = "local-asr"

        def transcribe(self, **_: object) -> TranscriptionResult:
            raise TranscriptionError(
                TranscriptionFailureCode.PROVIDER_FAILED, "local failed", retryable=True
            )

    registry = TranscriptionProviderRegistry([_FailingLocal(), openai])
    local_options = TranscriptionOptions(model=LOCAL)
    with pytest.raises(TranscriptionError):
        registry.get(local_options.model.provider_id).transcribe(
            audio=BytesIO(b""), options=local_options
        )
    assert transport.calls == 0  # a local failure never falls back to cloud

    # A local selection handed to the OpenAI adapter is refused, not proxied.
    with pytest.raises(TranscriptionError) as raised:
        openai.transcribe(audio=BytesIO(b""), options=local_options)
    assert raised.value.code is TranscriptionFailureCode.MODEL_NOT_INSTALLED
    assert transport.calls == 0


def test_key_is_not_retained_by_the_provider(tmp_path: Path) -> None:
    secrets = _secrets(tmp_path, OPENAI_API_KEY=KEY)
    provider = OpenAITranscriptionProvider(
        secrets=secrets, transport=FakeOpenAITransport()
    )
    assert KEY not in repr(vars(provider))
    assert KEY not in repr(secrets)
