"""Siembra un job COMPLETED con N segmentos sinteticos en una base TEMPORAL (V0-06).

Uso: seed_segment_rows.py <voz.sqlite3> <project_id> <media_asset_id> [N]
Imprime el id del job. Nunca apuntar a la base real del propietario.
"""

import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from voz.application.job_runner import transcript_id_for
from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.segment import Segment
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteSegmentRepository,
    SqliteTranscriptionJobRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)

DESCRIPTOR = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/fake-asr",
    revision="f" * 40,
)
WORDS = [
    "alfa",
    "bravo",
    "charlie",
    "delta",
    "eco",
    "foxtrot",
    "golf",
    "hotel",
    "india",
    "juliett",
    "kilo",
    "lima",
]


def main() -> None:
    db, project, asset = Path(sys.argv[1]), UUID(sys.argv[2]), UUID(sys.argv[3])
    count = int(sys.argv[4]) if len(sys.argv) > 4 else 2000
    engine = create_sqlite_engine(db.absolute())
    now = datetime.now(UTC)
    job = TranscriptionJob.create(
        job_id=uuid4(), project_id=project, media_asset_id=asset, now=now
    )
    job = replace(job, state=TranscriptionJobState.COMPLETED, progress=1.0)
    SqliteTranscriptionJobRepository(engine).add(job)
    SqliteTranscriptionJobSelectionRepository(engine).add(
        JobSelection(
            job_id=job.id,
            option_id="option-v1-fixture",
            model=DESCRIPTOR,
            execution=None,
            language=None,
            created_at=now,
        )
    )
    transcript = Transcript(project, asset, id=transcript_id_for(job.id), language="es")
    SqliteTranscriptRepository(engine).add(transcript)
    segments = SqliteSegmentRepository(engine)
    for i in range(count):
        # Largos variables (1 a 4 lineas) para forzar alturas de fila distintas.
        text = f"Segmento {i:04d} " + " ".join(
            WORDS[(i + k) % len(WORDS)] for k in range(8 + (i * 7) % 40)
        )
        segments.add(Segment(transcript.id, i * 3000, i * 3000 + 2900, text))
    print(job.id)
    engine.dispose()


main()
