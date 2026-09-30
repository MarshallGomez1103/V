"""SQLite adapter for reproducible per-job selection snapshots."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import Engine, RowMapping, insert, select, update

from voz.application.asr_device_selection import (
    ComputeDevice,
    ExecutionDecision,
    FallbackReason,
)
from voz.application.ports.diarization import DiarizationOptions, SpeakerCountHint
from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)
from voz.infrastructure.persistence.schema import transcription_job_selections


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _object(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, str):
        raise TypeError(f"persisted {field} must be a string")
    raw: object = json.loads(value)
    if not isinstance(raw, dict):
        raise TypeError(f"persisted {field} must contain an object")
    return cast(dict[str, object], raw)


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"persisted {field} must be a string")
    return value


def _optional_text(value: object, *, field: str) -> str | None:
    return None if value is None else _text(value, field=field)


def _strings(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise TypeError(f"persisted {field} must be a list")
    return [_text(item, field=field) for item in cast(list[object], value)]


def _model_json(model: ModelDescriptor) -> str:
    profile = model.profile
    return _dump(
        {
            "provider_id": model.provider_id,
            "model_id": model.model_id,
            "display_name": model.display_name,
            "capabilities": sorted(item.value for item in model.capabilities),
            "source": model.source,
            "revision": model.revision,
            "profile": None
            if profile is None
            else {
                "name": profile.name.value,
                "device_preference": profile.device_preference.value,
                "gpu_precisions": [item.value for item in profile.gpu_precisions],
                "cpu_precision": profile.cpu_precision.value,
            },
        }
    )


def _model_from_json(value: object) -> ModelDescriptor:
    data = _object(value, field="model_json")
    raw_profile = data.get("profile")
    profile: ProcessingProfile | None = None
    if raw_profile is not None:
        if not isinstance(raw_profile, dict):
            raise TypeError("persisted profile must be an object")
        profile_data = cast(dict[str, object], raw_profile)
        profile = ProcessingProfile(
            name=ProcessingProfileName(_text(profile_data.get("name"), field="name")),
            device_preference=DevicePreference(
                _text(profile_data.get("device_preference"), field="device_preference")
            ),
            gpu_precisions=tuple(
                ComputePrecision(item)
                for item in _strings(
                    profile_data.get("gpu_precisions"), field="gpu_precisions"
                )
            ),
            cpu_precision=ComputePrecision(
                _text(profile_data.get("cpu_precision"), field="cpu_precision")
            ),
        )
    return ModelDescriptor(
        provider_id=_text(data.get("provider_id"), field="provider_id"),
        model_id=_text(data.get("model_id"), field="model_id"),
        display_name=_text(data.get("display_name"), field="display_name"),
        capabilities=frozenset(
            ModelCapability(item)
            for item in _strings(data.get("capabilities"), field="capabilities")
        ),
        source=_optional_text(data.get("source"), field="source"),
        revision=_optional_text(data.get("revision"), field="revision"),
        profile=profile,
    )


def _execution_json(execution: ExecutionDecision | None) -> str | None:
    if execution is None:
        return None
    return _dump(
        {
            "device": execution.device.value,
            "precision": execution.precision.value,
            "fallback_reason": (
                None
                if execution.fallback_reason is None
                else execution.fallback_reason.value
            ),
        }
    )


def _execution_from_json(value: object) -> ExecutionDecision | None:
    if value is None:
        return None
    data = _object(value, field="execution_json")
    reason = _optional_text(data.get("fallback_reason"), field="fallback_reason")
    return ExecutionDecision(
        device=ComputeDevice(_text(data.get("device"), field="device")),
        precision=ComputePrecision(_text(data.get("precision"), field="precision")),
        fallback_reason=None if reason is None else FallbackReason(reason),
    )


def _diarization_json(options: DiarizationOptions | None) -> str | None:
    if options is None:
        return None
    hint = options.speakers
    return _dump(
        {
            "speakers": {
                "exact": hint.exact,
                "minimum": hint.minimum,
                "maximum": hint.maximum,
            }
        }
    )


def _optional_int(value: object, *, field: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise TypeError(f"persisted {field} must be an integer")
    return value


def _diarization_from_json(value: object) -> DiarizationOptions | None:
    if value is None:
        return None
    raw = _object(value, field="diarization_json").get("speakers")
    if not isinstance(raw, dict):
        raise TypeError("persisted speakers must be an object")
    hint = cast(dict[str, object], raw)
    return DiarizationOptions(
        SpeakerCountHint(
            exact=_optional_int(hint.get("exact"), field="exact"),
            minimum=_optional_int(hint.get("minimum"), field="minimum"),
            maximum=_optional_int(hint.get("maximum"), field="maximum"),
        )
    )


def _selection_values(selection: JobSelection) -> dict[str, object]:
    return {
        "job_id": str(selection.job_id),
        "option_id": selection.option_id,
        "provider_id": selection.model.provider_id,
        "model_id": selection.model.model_id,
        "source": selection.model.source,
        "revision": selection.model.revision,
        "language": selection.language,
        "model_json": _model_json(selection.model),
        "execution_json": _execution_json(selection.execution),
        "created_at": selection.created_at.astimezone(UTC).isoformat(),
        "diarization_json": _diarization_json(selection.diarization),
        "diarization_error_code": selection.diarization_error_code,
    }


def _selection_from_row(row: RowMapping) -> JobSelection:
    return JobSelection(
        job_id=UUID(_text(row["job_id"], field="job_id")),
        option_id=_text(row["option_id"], field="option_id"),
        model=_model_from_json(row["model_json"]),
        execution=_execution_from_json(row["execution_json"]),
        language=_optional_text(row["language"], field="language"),
        created_at=datetime.fromisoformat(_text(row["created_at"], field="created_at")),
        diarization=_diarization_from_json(row["diarization_json"]),
        diarization_error_code=_optional_text(
            row["diarization_error_code"], field="diarization_error_code"
        ),
    )


class SqliteTranscriptionJobSelectionRepository:
    """One selection row per job, keyed by the job identity.

    Immutable except for ``diarization_error_code``, recorded once by the runner.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, selection: JobSelection) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                insert(transcription_job_selections).values(
                    _selection_values(selection)
                )
            )

    def get(self, job_id: UUID) -> JobSelection | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(transcription_job_selections).where(
                        transcription_job_selections.c.job_id == str(job_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
        return None if row is None else _selection_from_row(row)

    def record_diarization_error(self, job_id: UUID, code: str) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                update(transcription_job_selections)
                .where(transcription_job_selections.c.job_id == str(job_id))
                .values(diarization_error_code=code)
            )


__all__ = ["SqliteTranscriptionJobSelectionRepository"]
