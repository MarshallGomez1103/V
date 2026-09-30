"""Options policy tests use only canonical values, never native ASR runtimes."""

from dataclasses import replace

import pytest

from voz.application.asr_device_selection import (
    ComputeDevice,
    FallbackReason,
    HardwareCapabilities,
)
from voz.application.get_transcription_options import (
    GetTranscriptionOptions,
    option_identity,
)
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)

MODEL = ModelDescriptor(
    provider_id="local-asr",
    model_id="model",
    display_name="Known model",
    source="publisher/model",
    revision="a" * 40,
    profile=ProcessingProfile(
        ProcessingProfileName.FAST,
        DevicePreference.GPU_PREFERRED,
        (ComputePrecision.FLOAT16,),
        ComputePrecision.INT8,
    ),
    capabilities=frozenset(
        {ModelCapability.TRANSCRIPTION, ModelCapability.TRANSLATION}
    ),
)


class Catalog:
    def __init__(self, registered: bool = True, model: ModelDescriptor = MODEL) -> None:
        self.model = model
        self.registered = registered

    def list_models(self) -> tuple[ModelRegistration, ...]:
        return (
            ModelRegistration(
                self.model,
                InstallationStatus.REGISTERED
                if self.registered
                else InstallationStatus.NOT_REGISTERED,
                self.registered,
            ),
        )


class Runtime:
    def __init__(
        self,
        available: bool = True,
        cuda: bool = False,
        measured: HardwareCapabilities | None = None,
    ) -> None:
        self.available = available
        self.cuda = cuda
        self.measured = measured

    def probe(self, provider_id: str) -> RuntimeAvailability:
        assert provider_id == MODEL.provider_id
        return RuntimeAvailability(
            self.available,
            self.measured
            or HardwareCapabilities(
                frozenset({ComputePrecision.FLOAT16}) if self.cuda else frozenset(),
                frozenset({ComputePrecision.INT8}),
            ),
            frozenset({ModelCapability.TRANSCRIPTION}),
        )


@pytest.mark.parametrize("registered", [False, True])
@pytest.mark.parametrize("available", [False, True])
def test_registration_runtime_and_start_are_distinct(
    registered: bool, available: bool
) -> None:
    option = (
        GetTranscriptionOptions(Catalog(registered), Runtime(available))
        .execute()
        .options[0]
    )
    assert option.runtime_available is available
    assert option.option_id == option_identity(MODEL)
    assert option.can_start is (registered and available)
    assert ("model_not_registered" in option.blocking_reasons) is (not registered)
    assert ("runtime_unavailable" in option.blocking_reasons) is (not available)
    assert option.capabilities == (ModelCapability.TRANSCRIPTION,)
    assert (option.recommendation is not None) is (registered and available)


@pytest.mark.parametrize("cuda", [False, True])
def test_execution_preserves_selection_and_fallback(cuda: bool) -> None:
    option = GetTranscriptionOptions(Catalog(), Runtime(cuda=cuda)).execute().options[0]
    assert option.execution is not None
    assert option.execution.device is (
        ComputeDevice.CUDA if cuda else ComputeDevice.CPU
    )
    assert option.execution.fallback_reason is (
        None if cuda else FallbackReason.CUDA_UNAVAILABLE
    )
    assert option.device_name is None
    assert option.recommendation is not None
    assert option.recommendation.reason == "default_compatible_profile"


def test_identity_is_stable_and_covers_reproducible_profile_not_label() -> None:
    assert option_identity(MODEL) == option_identity(
        replace(MODEL, display_name="Renamed")
    )
    assert option_identity(MODEL) != option_identity(replace(MODEL, revision="b" * 40))
    assert MODEL.profile is not None
    assert option_identity(MODEL) != option_identity(
        replace(
            MODEL,
            profile=replace(MODEL.profile, cpu_precision=ComputePrecision.FLOAT16),
        )
    )


def test_known_unpinned_model_cannot_start_and_has_no_recommendation() -> None:
    model = replace(MODEL, source=None, revision=None)
    option = (
        GetTranscriptionOptions(Catalog(False, model), Runtime()).execute().options[0]
    )
    assert "revision_unpinned" in option.blocking_reasons
    assert not option.can_start
    assert option.recommendation is None


def test_compatible_quality_does_not_imply_recommended() -> None:
    assert MODEL.profile is not None
    model = replace(
        MODEL, profile=replace(MODEL.profile, name=ProcessingProfileName.QUALITY)
    )
    option = (
        GetTranscriptionOptions(Catalog(model=model), Runtime()).execute().options[0]
    )
    assert option.can_start
    assert option.recommendation is None


@pytest.mark.parametrize("case", ["no_compute", "no_transcription", "files_missing"])
def test_observed_blockers_prevent_start_and_recommendation(case: str) -> None:
    class ObservedCatalog(Catalog):
        def list_models(self) -> tuple[ModelRegistration, ...]:
            return (
                ModelRegistration(
                    MODEL, InstallationStatus.REGISTERED, case != "files_missing"
                ),
            )

    class ObservedRuntime(Runtime):
        def probe(self, provider_id: str) -> RuntimeAvailability:
            result = super().probe(provider_id)
            if case == "no_compute":
                return replace(
                    result, hardware=HardwareCapabilities(frozenset(), frozenset())
                )
            if case == "no_transcription":
                return replace(result, capabilities=frozenset())
            return result

    option = (
        GetTranscriptionOptions(ObservedCatalog(), ObservedRuntime())
        .execute()
        .options[0]
    )
    assert not option.can_start
    assert option.recommendation is None
    reason = {
        "no_compute": "execution_unavailable",
        "no_transcription": "transcription_unavailable",
        "files_missing": "model_files_missing",
    }[case]
    assert reason in option.blocking_reasons


def test_gpu_precision_fallback_reason_is_preserved() -> None:
    class UnsupportedGpu(Runtime):
        def probe(self, provider_id: str) -> RuntimeAvailability:
            return replace(
                super().probe(provider_id),
                hardware=HardwareCapabilities(
                    frozenset({ComputePrecision.INT8_FLOAT16}),
                    frozenset({ComputePrecision.INT8}),
                ),
            )

    option = GetTranscriptionOptions(Catalog(), UnsupportedGpu()).execute().options[0]
    assert option.execution is not None
    assert option.execution.fallback_reason is FallbackReason.CUDA_PRECISION_UNSUPPORTED


def test_option_identity_includes_provider_model_source_and_profile() -> None:
    assert MODEL.profile is not None
    variants = (
        MODEL,
        replace(MODEL, provider_id="other"),
        replace(MODEL, model_id="other"),
        replace(MODEL, source="other/source"),
        replace(
            MODEL, profile=replace(MODEL.profile, name=ProcessingProfileName.QUALITY)
        ),
    )
    assert len({option_identity(item) for item in variants}) == len(variants)


def _measured_option(model_id: str, registered: bool = True, **memory: int | None):
    hardware = HardwareCapabilities(
        frozenset({ComputePrecision.FLOAT16}),
        frozenset({ComputePrecision.INT8}),
        gpu_name="RTX 4060 Laptop GPU",
        **memory,
    )
    catalog = Catalog(registered, replace(MODEL, model_id=model_id))
    return (
        GetTranscriptionOptions(catalog, Runtime(measured=hardware))
        .execute()
        .options[0]
    )


def test_measured_vram_drives_recommendation_and_device_name() -> None:
    turbo = _measured_option("turbo", vram_total_mib=8188, vram_free_mib=7000)
    large = _measured_option("large-v3", vram_total_mib=8188, vram_free_mib=7000)

    assert turbo.recommendation is not None
    assert (turbo.recommendation.recommended, turbo.recommendation.reason) == (
        True,
        "gpu_fast_default",
    )
    assert large.recommendation is not None
    assert (large.recommendation.recommended, large.recommendation.reason) == (
        False,
        "gpu_quality_fits",
    )
    assert turbo.device_name == "RTX 4060 Laptop GPU"


def test_measured_recommendation_does_not_depend_on_installation() -> None:
    option = _measured_option(
        "turbo", registered=False, vram_total_mib=8188, vram_free_mib=7000
    )

    assert option.can_start is False
    assert option.recommendation is not None
    assert option.recommendation.reason == "gpu_fast_default"


def test_unmeasured_hardware_keeps_legacy_recommendation() -> None:
    option = _measured_option("turbo")

    assert option.recommendation is not None
    assert option.recommendation.reason == "default_compatible_profile"
