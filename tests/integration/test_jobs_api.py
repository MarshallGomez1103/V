"""ASGI coverage of the jobs contract over SQLite, a fake provider and the runner."""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, ClassVar, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from starlette.types import Message

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.create_transcription_job import CreateTranscriptionJob
from voz.application.get_transcription_options import (
    GetTranscriptionOptions,
    option_identity,
)
from voz.application.job_runner import JobRunner, transcript_id_for
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
)
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
    TranscriptionWord,
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
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import TranscriptionJobState
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteTranscriptionJobRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.schema import metadata
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)
from voz.interfaces.api.jobs import create_jobs_router

REPOSITORY_ROOT = Path(__file__).parents[2]
WAV_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/media/synthetic-tone.wav"
NOW = datetime(2026, 9, 21, 9, tzinfo=UTC)
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
    def __init__(self, registered: bool) -> None:
        self.registered = registered

    def list_models(self) -> tuple[ModelRegistration, ...]:
        status = (
            InstallationStatus.REGISTERED
            if self.registered
            else InstallationStatus.NOT_REGISTERED
        )
        return (ModelRegistration(MODEL, status, self.registered),)


class Runtime:
    def probe(self, provider_id: str) -> RuntimeAvailability:
        return RuntimeAvailability(
            True,
            HardwareCapabilities(frozenset(), frozenset({ComputePrecision.INT8})),
            frozenset({ModelCapability.TRANSCRIPTION}),
        )


class Provider:
    provider_id = "fake-asr"
    prompts: ClassVar[list[str | None]] = []

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        del audio, cancellation
        Provider.prompts.append(options.prompt)
        words = (TranscriptionWord(0, 100, " ho"), TranscriptionWord(100, 250, "la"))
        return TranscriptionResult(
            (TranscriptionSegment(0, 250, "hola", words=words),), "es"
        )


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
    def __init__(self, tmp_path: Path, *, registered: bool = True) -> None:
        self.engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
        metadata.create_all(self.engine)
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
        self.runner = JobRunner(
            jobs=jobs,
            selections=selections,
            media_assets=SqliteMediaAssetRepository(self.engine),
            transcripts=transcripts,
            segments=segments,
            checkpoints=SqliteTranscriptionCheckpointStore(self.engine),
            provider_for=lambda selection: Provider(),
            audio_source_for=lambda project_id, media_asset_id: (
                FileSystemInferenceAudioSource(root, project_id, media_asset_id)
            ),
            audio_preparer=Preparer(),
        )
        create_job = CreateTranscriptionJob(
            GetTranscriptionOptions(Catalog(registered), Runtime()),
            SqliteProjectRepository(self.engine),
            SqliteMediaAssetRepository(self.engine),
            jobs,
            selections,
        )
        self.app = FastAPI()
        self.app.include_router(
            create_jobs_router(
                create_job,
                jobs,
                selections,
                transcripts,
                segments,
                self.runner,
                checkpoints=SqliteTranscriptionCheckpointStore(self.engine),
            )
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        query: str = "",
        body: object | None = None,
    ) -> tuple[int, dict[str, object]]:
        return asyncio.run(_request(self.app, method, path, query, body))

    def create_body(self, **overrides: object) -> dict[str, object]:
        body: dict[str, object] = {
            "project_id": str(self.project.id),
            "media_asset_id": str(self.asset.id),
            "option_id": option_identity(MODEL),
            "language": "es",
        }
        body.update(overrides)
        return body

    def close(self) -> None:
        self.runner.stop()
        self.engine.dispose()


async def _request(
    app: FastAPI,
    method: str,
    path: str,
    query: str,
    body: object | None,
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
            "query_string": query.encode(),
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


def test_create_then_complete_and_read_segments(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        status, created = harness.request(
            "POST", "/api/jobs", body=harness.create_body()
        )
        assert status == 201
        assert created["state"] == "QUEUED"
        assert created["progress"] == 0.0
        assert created["error_code"] is None
        assert created["transcript_id"] is None
        selection = cast(dict[str, object], created["selection"])
        assert selection["option_id"] == option_identity(MODEL)
        assert selection["provider_id"] == "fake-asr"
        assert selection["revision"] == "e" * 40
        assert selection["language"] == "es"
        assert selection["profile"] == {
            "name": "fast",
            "device_preference": "gpu_preferred",
            "gpu_precisions": ["float16"],
            "cpu_precision": "int8",
        }
        assert selection["execution"] == {
            "device": "cpu",
            "precision": "int8",
            "fallback_reason": "cuda_unavailable",
        }
        assert str(created["created_at"]).endswith("+00:00")
        assert str(tmp_path) not in json.dumps(created)

        harness.runner.start()
        assert harness.runner.wait_idle(10.0)

        job_id = str(created["id"])
        status, fetched = harness.request("GET", f"/api/jobs/{job_id}")
        assert status == 200
        assert fetched["state"] == "COMPLETED"
        assert fetched["progress"] == 1.0
        transcript_id = fetched["transcript_id"]
        assert isinstance(transcript_id, str)

        status, listed = harness.request(
            "GET", "/api/jobs", query=f"project_id={harness.project.id}"
        )
        assert status == 200
        assert [item["id"] for item in cast(list[dict[str, object]], listed["jobs"])]
        assert cast(list[dict[str, object]], listed["jobs"])[0]["id"] == job_id

        status, segments = harness.request(
            "GET", f"/api/transcripts/{transcript_id}/segments"
        )
        assert status == 200
        items = cast(list[dict[str, object]], segments["segments"])
        assert [(i["start_ms"], i["end_ms"], i["text"]) for i in items] == [
            (0, 250, "hola")
        ]
        assert items[0]["words"] == [
            {"start_ms": 0, "end_ms": 100, "text": "ho", "speaker_id": None},
            {"start_ms": 100, "end_ms": 250, "text": "la", "speaker_id": None},
        ]

        status, conflict = harness.request("POST", f"/api/jobs/{job_id}/cancel")
        assert status == 409
        assert _detail(conflict)["code"] == "job_terminal"
    finally:
        harness.close()


def test_create_errors_follow_contract(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        status, body = harness.request(
            "POST", "/api/jobs", body=harness.create_body(project_id=str(uuid4()))
        )
        assert (status, _detail(body)["code"]) == (404, "project_not_found")

        status, body = harness.request(
            "POST",
            "/api/jobs",
            body=harness.create_body(media_asset_id=str(uuid4())),
        )
        assert (status, _detail(body)["code"]) == (404, "media_asset_not_found")

        status, body = harness.request(
            "POST", "/api/jobs", body=harness.create_body(option_id="option-v1-x")
        )
        assert (status, _detail(body)["code"]) == (404, "option_unknown")

        status, first = harness.request("POST", "/api/jobs", body=harness.create_body())
        assert status == 201
        status, body = harness.request("POST", "/api/jobs", body=harness.create_body())
        assert (status, _detail(body)["code"]) == (409, "job_already_active")

        status, cancelled = harness.request("POST", f"/api/jobs/{first['id']}/cancel")
        assert status == 202
        assert cancelled["state"] in {"CANCELLING", "CANCELLED"}

        status, body = harness.request("GET", f"/api/jobs/{uuid4()}")
        assert (status, _detail(body)["code"]) == (404, "job_not_found")
        status, body = harness.request("POST", f"/api/jobs/{uuid4()}/cancel")
        assert (status, _detail(body)["code"]) == (404, "job_not_found")
        status, body = harness.request("GET", f"/api/transcripts/{uuid4()}/segments")
        assert (status, _detail(body)["code"]) == (404, "transcript_not_found")
    finally:
        harness.close()


def test_non_startable_option_returns_blocking_reasons(tmp_path: Path) -> None:
    harness = Harness(tmp_path, registered=False)
    try:
        status, body = harness.request("POST", "/api/jobs", body=harness.create_body())
        assert status == 409
        detail = _detail(body)
        assert detail["code"] == "option_not_startable"
        assert "model_not_registered" in cast(list[str], detail["blocking_reasons"])
    finally:
        harness.close()


def test_job_defaults_to_the_default_profile_and_exposes_it(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        status, created = harness.request(
            "POST", "/api/jobs", body=harness.create_body()
        )

        assert status == 201
        selection = cast(dict[str, object], created["selection"])
        profile = cast(dict[str, object], selection["quality_profile"])
        assert (profile["name"], profile["version"], profile["vad"]) == (
            "default",
            1,
            None,
        )
        assert selection["glossary"] == []
    finally:
        harness.close()


def test_job_stores_the_requested_profile_with_effective_parameters(
    tmp_path: Path,
) -> None:
    harness = Harness(tmp_path)
    try:
        status, created = harness.request(
            "POST", "/api/jobs", body=harness.create_body(profile="academic")
        )
        assert status == 201
        status, fetched = harness.request("GET", f"/api/jobs/{created['id']}")

        selection = cast(dict[str, object], fetched["selection"])
        profile = cast(dict[str, object], selection["quality_profile"])
        assert profile["name"] == "academic"
        assert profile["condition_on_previous_text"] is False
        assert (
            cast(dict[str, object], profile["vad"])["min_silence_duration_ms"] == 1000
        )
    finally:
        harness.close()


def test_unknown_profile_is_a_typed_422_and_creates_no_job(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        status, body = harness.request(
            "POST", "/api/jobs", body=harness.create_body(profile="nope")
        )

        assert status == 422
        assert _detail(body)["code"] == "quality_profile_unknown"
        _, listed = harness.request(
            "GET", "/api/jobs", query=f"project_id={harness.project.id}"
        )
        assert listed["jobs"] == []
    finally:
        harness.close()


def test_prompt_is_stripped_snapshotted_and_given_to_the_engine(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    Provider.prompts.clear()
    try:
        status, created = harness.request(
            "POST",
            "/api/jobs",
            body=harness.create_body(prompt="  Clase de biología. Usa tildes.  "),
        )
        assert status == 201
        selection = cast(dict[str, object], created["selection"])
        assert selection["prompt"] == "Clase de biología. Usa tildes."

        harness.runner.start()
        assert harness.runner.wait_idle(10.0)

        assert Provider.prompts == ["Clase de biología. Usa tildes."]
        _, fetched = harness.request("GET", f"/api/jobs/{created['id']}")
        assert cast(dict[str, object], fetched["selection"])["prompt"] == (
            "Clase de biología. Usa tildes."
        )
    finally:
        harness.close()


@pytest.mark.parametrize("prompt", [None, "", "   \n "])
def test_blank_or_missing_prompt_is_null(tmp_path: Path, prompt: str | None) -> None:
    harness = Harness(tmp_path)
    try:
        body = (
            harness.create_body()
            if prompt is None
            else harness.create_body(prompt=prompt)
        )
        status, created = harness.request("POST", "/api/jobs", body=body)

        assert status == 201
        assert cast(dict[str, object], created["selection"])["prompt"] is None
    finally:
        harness.close()


def test_prompt_limit_is_600_characters_after_strip(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        status, _ = harness.request(
            "POST", "/api/jobs", body=harness.create_body(prompt=" " + "a" * 600 + " ")
        )
        assert status == 201

        status, body = harness.request(
            "POST", "/api/jobs", body=harness.create_body(prompt="a" * 601)
        )
        assert (status, _detail(body)["code"]) == (422, "job_prompt_invalid")
        jobs = SqliteTranscriptionJobRepository(harness.engine)
        assert len(jobs.list_by_project(harness.project.id)) == 1  # only the valid one
    finally:
        harness.close()


def test_job_view_carries_stage_timing_fields(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        _, created = harness.request("POST", "/api/jobs", body=harness.create_body())
        assert created["started_at"] is None  # still queued
        assert created["stage_progress"] is None
        assert created["eta_seconds"] is None

        harness.runner.start()
        assert harness.runner.wait_idle(10.0)
        _, fetched = harness.request("GET", f"/api/jobs/{created['id']}")

        assert isinstance(fetched["started_at"], str)
        assert isinstance(fetched["stage_started_at"], str)
        assert fetched["stage_progress"] is None  # a terminal job has no stage
        assert fetched["eta_seconds"] is None
    finally:
        harness.close()


def test_transcript_id_is_exposed_as_soon_as_the_text_exists(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        _, created = harness.request("POST", "/api/jobs", body=harness.create_body())
        jobs = SqliteTranscriptionJobRepository(harness.engine)
        job = jobs.get(UUID(str(created["id"])))
        assert job is not None
        for step, state in enumerate(
            (
                TranscriptionJobState.PROBING,
                TranscriptionJobState.PREPROCESSING,
                TranscriptionJobState.TRANSCRIBING,
                TranscriptionJobState.ALIGNING,
                TranscriptionJobState.DIARIZING,
            ),
            start=1,
        ):
            job = job.transition_to(state, at=job.updated_at + timedelta(seconds=step))
            if state is TranscriptionJobState.TRANSCRIBING:
                jobs.save(job)
                _, view = harness.request("GET", f"/api/jobs/{job.id}")
                assert view["transcript_id"] is None
        job = job.with_stage_progress(0.5, progress=0.89, at=job.updated_at)
        jobs.save(job)
        SqliteTranscriptRepository(harness.engine).add(
            Transcript(
                job.project_id,
                job.media_asset_id,
                id=transcript_id_for(job.id),
                language="es",
                created_at=NOW,
            )
        )

        _, view = harness.request("GET", f"/api/jobs/{job.id}")

        assert view["state"] == "DIARIZING"
        assert view["transcript_id"] == str(transcript_id_for(job.id))
        assert view["progress"] == 0.89
        assert view["stage_progress"] == 0.5
        status, segments = harness.request(
            "GET", f"/api/transcripts/{view['transcript_id']}/segments"
        )
        assert status == 200
        assert segments == {"segments": []}
    finally:
        harness.close()


def test_preview_lists_checkpointed_segments_and_only_the_new_ones(
    tmp_path: Path,
) -> None:
    harness = Harness(tmp_path)
    try:
        _, created = harness.request("POST", "/api/jobs", body=harness.create_body())
        path = f"/api/jobs/{created['id']}/preview"
        assert harness.request("GET", path) == (200, {"segments": []})  # nothing yet

        harness.runner.start()
        assert harness.runner.wait_idle(10.0)

        assert harness.request("GET", path) == (
            200,
            {"segments": [{"start_ms": 0, "end_ms": 250, "text": "hola"}]},
        )
        assert harness.request("GET", path, query="after_ms=100")[1]["segments"] != []
        assert harness.request("GET", path, query="after_ms=250") == (
            200,
            {"segments": []},
        )
        status, _ = harness.request("GET", path, query="after_ms=-1")
        assert status == 422
    finally:
        harness.close()


def test_preview_of_an_unknown_job_is_404(tmp_path: Path) -> None:
    harness = Harness(tmp_path)
    try:
        status, body = harness.request("GET", f"/api/jobs/{uuid4()}/preview")

        assert (status, _detail(body)["code"]) == (404, "job_not_found")
    finally:
        harness.close()
