"""POST /api/jobs diarization option: validation, availability and JobView."""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from starlette.types import Message

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.assign_speakers import AssignSpeakers
from voz.application.create_transcription_job import CreateTranscriptionJob
from voz.application.get_transcription_options import (
    GetTranscriptionOptions,
    option_identity,
)
from voz.application.job_runner import JobRunner
from voz.application.ports.diarization import (
    DiarizationError,
    DiarizationFailureCode,
    DiarizationOptions,
    DiarizationResult,
)
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
)
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
)
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)
from voz.domain.entities.project import Project
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import upgrade_to_head
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteSpeakerRepository,
    SqliteSpeakerTurnRepository,
    SqliteTranscriptionJobRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)
from voz.interfaces.api.jobs import create_jobs_router

REPOSITORY_ROOT = Path(__file__).parents[2]
WAV_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/media/synthetic-tone.wav"
NOW = datetime(2026, 9, 30, 9, tzinfo=UTC)
MODEL = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    source="example/fake-asr",
    revision="e" * 40,
    profile=ProcessingProfile(
        ProcessingProfileName.FAST,
        DevicePreference.GPU_PREFERRED,
        (ComputePrecision.FLOAT16,),
        ComputePrecision.INT8,
    ),
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
)


class Catalog:
    def list_models(self) -> tuple[ModelRegistration, ...]:
        return (ModelRegistration(MODEL, InstallationStatus.REGISTERED, True),)


class Runtime:
    def probe(self, provider_id: str) -> RuntimeAvailability:
        return RuntimeAvailability(
            True,
            HardwareCapabilities(frozenset(), frozenset({ComputePrecision.INT8})),
            frozenset({ModelCapability.TRANSCRIPTION}),
        )


class Asr:
    provider_id = "fake-asr"

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        del audio, options, cancellation
        return TranscriptionResult((TranscriptionSegment(0, 250, "hola"),), "es")


class Diarizer:
    provider_id = "fake-diarization"

    def __init__(self, error: DiarizationError | None) -> None:
        self.error = error
        self.options: list[DiarizationOptions] = []

    def diarize(
        self,
        *,
        audio: BinaryIO,
        options: DiarizationOptions,
        cancellation: TranscriptionCancellationToken | None = None,
        on_progress: object = None,
    ) -> DiarizationResult:
        del audio, cancellation
        self.options.append(options)
        if self.error is not None:
            raise self.error
        return DiarizationResult(())


class Availability:
    def __init__(self, models: bool, runtime: bool) -> None:
        self.models = models
        self.runtime = runtime

    def runtime_available(self) -> bool:
        return self.runtime

    def models_installed(self) -> bool:
        return self.models

    def is_available(self) -> bool:
        return self.models and self.runtime


class Preparer:
    def prepare(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
        cancellation: MediaNormalizationCancellationToken | None = None,
        on_progress: object = None,
    ) -> None:
        raise AssertionError("derivative already exists")


class Harness:
    def __init__(
        self,
        tmp_path: Path,
        *,
        models: bool = True,
        runtime: bool = True,
        error: DiarizationError | None = None,
    ) -> None:
        self.engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
        upgrade_to_head(self.engine)
        self.project = Project("Demo", created_at=NOW)
        SqliteProjectRepository(self.engine).add(self.project)
        self.asset = MediaAsset(
            self.project.id, "a" * 64, "tone.wav", 8_044, duration_ms=250
        )
        SqliteMediaAssetRepository(self.engine).add(self.asset)
        root = tmp_path / "data"
        target = root / "projects" / str(self.project.id) / "derivatives"
        target.mkdir(parents=True)
        shutil.copyfile(WAV_FIXTURE, target / f"{self.asset.id}.inference.wav")

        jobs = SqliteTranscriptionJobRepository(self.engine)
        selections = SqliteTranscriptionJobSelectionRepository(self.engine)
        transcripts = SqliteTranscriptRepository(self.engine)
        segments = SqliteSegmentRepository(self.engine)
        self.diarizer = Diarizer(error)
        self.runner = JobRunner(
            jobs=jobs,
            selections=selections,
            media_assets=SqliteMediaAssetRepository(self.engine),
            transcripts=transcripts,
            segments=segments,
            checkpoints=SqliteTranscriptionCheckpointStore(self.engine),
            provider_for=lambda selection: Asr(),
            audio_source_for=lambda project_id, media_asset_id: (
                FileSystemInferenceAudioSource(root, project_id, media_asset_id)
            ),
            audio_preparer=Preparer(),
            diarization_provider_for=lambda: self.diarizer,
            assign_speakers=AssignSpeakers(
                transcripts,
                segments,
                SqliteSpeakerRepository(self.engine),
                SqliteSpeakerTurnRepository(self.engine),
            ),
        )
        create_job = CreateTranscriptionJob(
            GetTranscriptionOptions(Catalog(), Runtime()),
            SqliteProjectRepository(self.engine),
            SqliteMediaAssetRepository(self.engine),
            jobs,
            selections,
            Availability(models, runtime),
        )
        self.app = FastAPI()
        self.app.include_router(
            create_jobs_router(
                create_job, jobs, selections, transcripts, segments, self.runner
            )
        )

    def request(
        self, method: str, path: str, body: object | None = None
    ) -> tuple[int, dict[str, object]]:
        return asyncio.run(_request(self.app, method, path, body))

    def post(self, **overrides: object) -> tuple[int, dict[str, object]]:
        body: dict[str, object] = {
            "project_id": str(self.project.id),
            "media_asset_id": str(self.asset.id),
            "option_id": option_identity(MODEL),
        }
        body.update(overrides)
        return self.request("POST", "/api/jobs", body)

    def close(self) -> None:
        self.runner.stop()
        self.engine.dispose()


async def _request(
    app: FastAPI, method: str, path: str, body: object | None
) -> tuple[int, dict[str, object]]:
    payload = b"" if body is None else json.dumps(body).encode()
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
            "root_path": "",
        },
        receive,
        send,
    )
    raw = b"".join(cast(bytes, message.get("body", b"")) for message in messages)
    return int(cast(int, messages[0]["status"])), cast(
        dict[str, object], json.loads(raw)
    )


def _detail(body: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], body["detail"])


def _diarization(view: dict[str, object]) -> dict[str, object]:
    selection = cast(dict[str, object], view["selection"])
    return cast(dict[str, object], selection["diarization"])


def test_default_is_disabled(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        status, created = harness.post()

        assert status == 201
        assert _diarization(created) == {
            "enabled": False,
            "speakers": {"exact": None, "minimum": None, "maximum": None},
        }
        assert created["diarization_error_code"] is None
    finally:
        harness.close()


def test_enabled_request_is_snapshotted_and_runs(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        status, created = harness.post(
            diarization={"enabled": True, "speakers": {"minimum": 2, "maximum": 4}}
        )
        assert status == 201
        assert _diarization(created) == {
            "enabled": True,
            "speakers": {"exact": None, "minimum": 2, "maximum": 4},
        }

        harness.runner.start()
        assert harness.runner.wait_idle(10.0)

        status, fetched = harness.request("GET", f"/api/jobs/{created['id']}")
        assert status == 200
        assert fetched["state"] == "COMPLETED"
        assert fetched["diarization_error_code"] is None
        assert _diarization(fetched) == _diarization(created)
        assert harness.diarizer.options[0].speakers.minimum == 2
    finally:
        harness.close()


def test_disabled_flag_ignores_speaker_hint(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        status, created = harness.post(
            diarization={"enabled": False, "speakers": {"exact": 2}}
        )

        assert status == 201
        assert _diarization(created)["enabled"] is False
    finally:
        harness.close()


@pytest.mark.parametrize(
    "diarization",
    [
        "yes",
        [],
        {"enabled": "true"},
        {"enabled": 1},
        {"enabled": True, "extra": 1},
        {"enabled": True, "speakers": 2},
        {"enabled": True, "speakers": {"exact": 0}},
        {"enabled": True, "speakers": {"exact": -1}},
        {"enabled": True, "speakers": {"exact": 2.5}},
        {"enabled": True, "speakers": {"exact": True}},
        {"enabled": True, "speakers": {"exact": "2"}},
        {"enabled": True, "speakers": {"exact": 33}},
        {"enabled": True, "speakers": {"exact": 2, "maximum": 3}},
        {"enabled": True, "speakers": {"minimum": 4, "maximum": 2}},
        {"enabled": True, "speakers": {"median": 2}},
        {"enabled": False, "speakers": {"exact": 0}},
    ],
)
def test_invalid_options_are_422_with_stable_code(
    tmp_path: Path, diarization: object
) -> None:
    harness = Harness(tmp_path)
    try:
        status, body = harness.post(diarization=diarization)

        assert status == 422
        assert _detail(body)["code"] == "diarization_options_invalid"
        assert not SqliteTranscriptionJobRepository(harness.engine).list_by_project(
            harness.project.id
        )
    finally:
        harness.close()


def test_missing_models_are_409_and_create_nothing(tmp_path: Path) -> None:
    harness = Harness(tmp_path, models=False)
    try:
        status, body = harness.post(diarization={"enabled": True})

        assert status == 409
        assert _detail(body)["code"] == "diarization_models_missing"
        assert (
            SqliteTranscriptionJobRepository(harness.engine).list_by_project(
                harness.project.id
            )
            == ()
        )
        # Not asking for diarization still works without the models.
        status, _ = harness.post(diarization={"enabled": False})
        assert status == 201
    finally:
        harness.close()


def test_missing_runtime_is_diarization_unavailable(tmp_path: Path) -> None:
    # No runtime wins over missing models: downloading them would not help.
    harness = Harness(tmp_path, models=False, runtime=False)
    try:
        status, body = harness.post(diarization={"enabled": True})

        assert status == 409
        assert _detail(body)["code"] == "diarization_unavailable"
        assert not SqliteTranscriptionJobRepository(harness.engine).list_by_project(
            harness.project.id
        )
    finally:
        harness.close()


def test_failed_diarization_keeps_job_completed_with_error_code(
    tmp_path: Path,
) -> None:
    error = DiarizationError(DiarizationFailureCode.PROVIDER_FAILED, "/private/engine")
    harness = Harness(tmp_path, error=error)
    try:
        status, created = harness.post(diarization={"enabled": True})
        assert status == 201

        harness.runner.start()
        assert harness.runner.wait_idle(10.0)

        _, fetched = harness.request("GET", f"/api/jobs/{created['id']}")
        assert fetched["state"] == "COMPLETED"
        assert fetched["error_code"] is None
        assert fetched["diarization_error_code"] == "diarization_provider_failed"
        assert fetched["transcript_id"] is not None
        _, segments = harness.request(
            "GET", f"/api/transcripts/{fetched['transcript_id']}/segments"
        )
        assert [
            s["text"] for s in cast(list[dict[str, object]], segments["segments"])
        ] == ["hola"]
        assert "/private" not in json.dumps(fetched)
    finally:
        harness.close()
