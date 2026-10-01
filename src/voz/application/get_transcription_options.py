"""Stable, conservative options for future transcription selection."""

import hashlib
import json
from contextlib import suppress
from dataclasses import asdict, dataclass
from enum import StrEnum

from voz.application.asr_device_selection import (
    ComputeDevice,
    ExecutionDecision,
    select_execution,
)
from voz.application.hardware_recommendation import (
    Recommendation,
    is_measured,
    recommend,
)
from voz.application.ports.transcription import TranscriptionError
from voz.application.ports.transcription_options import (
    InstallationStatus,
    RuntimeAvailability,
    TranscriptionModelCatalog,
    TranscriptionRuntimeProbe,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ProcessingProfile,
    ProcessingProfileName,
)


class BlockingReason(StrEnum):
    MODEL_NOT_REGISTERED = "model_not_registered"
    MODEL_FILES_MISSING = "model_files_missing"
    REVISION_UNPINNED = "revision_unpinned"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    EXECUTION_UNAVAILABLE = "execution_unavailable"
    TRANSCRIPTION_UNAVAILABLE = "transcription_unavailable"


@dataclass(frozen=True, slots=True)
class TranscriptionOption:
    option_id: str
    provider_id: str
    model_id: str
    source: str | None
    revision: str | None
    profile: ProcessingProfile | None
    display_name: str
    installation_status: InstallationStatus
    files_available: bool
    runtime_available: bool
    can_start: bool
    capabilities: tuple[ModelCapability, ...]
    execution: ExecutionDecision | None
    device_name: str | None
    recommendation: Recommendation | None
    blocking_reasons: tuple[BlockingReason, ...]
    cloud: bool = False
    provider_label: str | None = None


@dataclass(frozen=True, slots=True)
class TranscriptionOptions:
    options: tuple[TranscriptionOption, ...]


_INSTALL_REASONS = {
    BlockingReason.MODEL_NOT_REGISTERED,
    BlockingReason.MODEL_FILES_MISSING,
}


def _device_name(
    runtime: RuntimeAvailability, execution: ExecutionDecision | None
) -> str | None:
    if execution is None:
        return None
    if runtime.device_name is not None:
        return runtime.device_name
    if execution.device is ComputeDevice.CUDA and runtime.hardware is not None:
        return runtime.hardware.gpu_name
    return None


def option_identity(descriptor: ModelDescriptor) -> str:
    """Versioned identity excludes labels, installation and transient hardware."""
    payload = (
        descriptor.provider_id,
        descriptor.model_id,
        descriptor.source,
        descriptor.revision,
        None if descriptor.profile is None else asdict(descriptor.profile),
    )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "option-v1-" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class GetTranscriptionOptions:
    catalog: TranscriptionModelCatalog
    runtime: TranscriptionRuntimeProbe

    def execute(self) -> TranscriptionOptions:
        registrations = self.catalog.list_models()
        runtimes = {
            provider: self.runtime.probe(provider)
            for provider in sorted(
                {item.descriptor.provider_id for item in registrations}
            )
        }
        options: list[TranscriptionOption] = []
        for registration in registrations:
            model = registration.descriptor
            runtime = runtimes[model.provider_id]
            reasons: list[BlockingReason] = []
            if registration.installation_status is not InstallationStatus.REGISTERED:
                reasons.append(BlockingReason.MODEL_NOT_REGISTERED)
            elif not registration.files_available:
                reasons.append(BlockingReason.MODEL_FILES_MISSING)
            if model.provenance is None and not registration.cloud:
                reasons.append(BlockingReason.REVISION_UNPINNED)
            if not runtime.available:
                reasons.append(BlockingReason.RUNTIME_UNAVAILABLE)
            execution = None
            local = not registration.cloud  # cloud: remote compute, no local plan
            if (
                local
                and runtime.available
                and runtime.hardware is not None
                and model.profile
            ):
                with suppress(TranscriptionError):
                    execution = select_execution(model.profile, runtime.hardware)
            if runtime.available and execution is None and local:
                reasons.append(BlockingReason.EXECUTION_UNAVAILABLE)
            capabilities = tuple(sorted(model.capabilities & runtime.capabilities))
            if ModelCapability.TRANSCRIPTION not in capabilities:
                reasons.append(BlockingReason.TRANSCRIPTION_UNAVAILABLE)
            recommendation = None
            hardware = runtime.hardware
            # ponytail: cloud is never recommended, not even by default.
            if not local:
                pass
            elif (
                hardware is not None
                and execution is not None
                and is_measured(hardware)
                and set(reasons) <= _INSTALL_REASONS
            ):
                # Measured hardware: fit recommendation, independent of installation.
                recommendation = recommend(model.model_id, hardware)
            elif (
                not reasons
                and model.profile
                and model.profile.name is ProcessingProfileName.FAST
            ):
                recommendation = Recommendation(True, "default_compatible_profile")
            options.append(
                TranscriptionOption(
                    option_id=option_identity(model),
                    provider_id=model.provider_id,
                    model_id=model.model_id,
                    source=model.source,
                    revision=model.revision,
                    profile=model.profile,
                    display_name=model.display_name,
                    installation_status=registration.installation_status,
                    files_available=registration.files_available,
                    runtime_available=runtime.available,
                    can_start=not reasons,
                    capabilities=capabilities,
                    execution=execution,
                    device_name=_device_name(runtime, execution),
                    recommendation=recommendation,
                    blocking_reasons=tuple(reasons),
                    cloud=registration.cloud,
                    provider_label=registration.provider_label,
                )
            )
        return TranscriptionOptions(
            tuple(sorted(options, key=lambda item: item.option_id))
        )


__all__ = [
    "BlockingReason",
    "GetTranscriptionOptions",
    "Recommendation",
    "TranscriptionOption",
    "TranscriptionOptions",
    "option_identity",
]
