"""The real app fails cloud jobs left by a restart instead of resuming them."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from voz.application.get_transcription_options import GetTranscriptionOptions
from voz.application.ports.speech_synthesis import (
    SynthesisLocality,
    SynthesisProviderInfo,
)
from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
)
from voz.bootstrap import DATABASE_FILENAME, create_app
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.synthesis_job import SynthesisJob
from voz.domain.entities.synthesis_request import SynthesisRequest
from voz.domain.entities.transcription_job import TranscriptionJob
from voz.infrastructure.paths import VozPaths
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteTranscriptionJobRepository,
)
from voz.infrastructure.persistence.synthesis import SqliteSynthesisJobRepository
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)
from voz.infrastructure.tts.fake import (
    FAKE_TTS_PROVIDER_ID,
    FakeSpeechSynthesisProvider,
    fake_tts_descriptor,
)

NOW = datetime(2026, 10, 21, 9, tzinfo=UTC)


class _CloudTts(FakeSpeechSynthesisProvider):
    def describe(self) -> SynthesisProviderInfo:
        return SynthesisProviderInfo(
            provider_id=FAKE_TTS_PROVIDER_ID,
            display_name="Fake cloud TTS",
            locality=SynthesisLocality.CLOUD,
        )


class _Catalog:
    def list_models(self) -> tuple[ModelRegistration, ...]:
        return (
            ModelRegistration(
                fake_tts_descriptor(), InstallationStatus.REGISTERED, True
            ),
        )


class _Offline:
    def list_models(self) -> tuple[ModelRegistration, ...]:
        return ()

    def probe(self, provider_id: str) -> RuntimeAvailability:
        return RuntimeAvailability(False)


def _app(paths: VozPaths) -> TestClient:
    return TestClient(
        create_app(
            paths=paths,
            transcription_options=GetTranscriptionOptions(_Offline(), _Offline()),
            synthesis_providers=[_CloudTts()],
            synthesis_catalog=_Catalog(),
        )
    )


def test_restart_fails_cloud_jobs_with_a_stable_code(tmp_path: Path) -> None:
    for name in ("data", "state"):
        (tmp_path / name).mkdir()
    paths = VozPaths(
        tmp_path / "config", tmp_path / "data", tmp_path / "cache", tmp_path / "state"
    )
    with _app(paths):  # first start: migrates the schema
        pass

    engine = create_sqlite_engine((paths.data / DATABASE_FILENAME).absolute())
    project = Project("Demo", created_at=NOW)
    SqliteProjectRepository(engine).add(project)
    asset = MediaAsset(project.id, "a" * 64, "tone.wav", 8_044, duration_ms=250)
    SqliteMediaAssetRepository(engine).add(asset)
    stt = TranscriptionJob.create(
        job_id=uuid4(), project_id=project.id, media_asset_id=asset.id, now=NOW
    )
    SqliteTranscriptionJobRepository(engine).add(stt)
    SqliteTranscriptionJobSelectionRepository(engine).add(
        JobSelection(
            job_id=stt.id,
            option_id="option-v1-openai",
            model=ModelDescriptor(
                provider_id="openai",
                model_id="whisper-1",
                display_name="OpenAI",
                capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
            ),
            execution=None,
            language=None,
            created_at=NOW,
        )
    )
    tts = SynthesisJob.create(
        job_id=uuid4(),
        request=SynthesisRequest(
            text="Hello there.",
            provider_id=FAKE_TTS_PROVIDER_ID,
            model_id="tone",
            voice_id="tone-low",
        ),
        chunks_total=1,
        now=NOW,
    )
    SqliteSynthesisJobRepository(engine).add(tts)
    engine.dispose()

    with _app(paths) as client:
        stt_view = client.get(f"/api/jobs/{stt.id}").json()
        tts_view = client.get(f"/api/synthesis/{tts.id}").json()

    assert (stt_view["state"], stt_view["error_code"]) == (
        "FAILED",
        "cloud_consent_expired",
    )
    assert (tts_view["state"], tts_view["error_code"]) == (
        "FAILED",
        "cloud_consent_expired",
    )
