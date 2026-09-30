"""POST /api/jobs maps the S14.05/S14.06 memory refusals to 409 with stable codes."""

from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voz.application.create_transcription_job import (
    CreateJobError,
    CreateJobFailureCode,
)
from voz.interfaces.api.jobs import create_jobs_router


class RefusingCreate:
    def __init__(self, error: CreateJobError) -> None:
        self.error = error

    def execute(self, **_: object) -> None:
        raise self.error


@pytest.mark.parametrize(
    "code",
    [CreateJobFailureCode.INSUFFICIENT_VRAM, CreateJobFailureCode.INSUFFICIENT_RAM],
)
def test_insufficient_memory_is_409_with_safe_detail(
    code: CreateJobFailureCode,
) -> None:
    error = CreateJobError(
        code, "Not enough memory.", required_mib=5000, available_mib=900
    )
    none = cast(Any, None)
    app = FastAPI()
    app.include_router(
        create_jobs_router(
            cast(Any, RefusingCreate(error)), none, none, none, none, none
        )
    )
    # TestClient is an httpx.Client; its own stubs resolve to Unknown under pyright.
    client = cast(httpx.Client, TestClient(app))  # pyright: ignore[reportUnknownArgumentType]

    response = client.post(
        "/api/jobs",
        json={
            "project_id": str(uuid4()),
            "media_asset_id": str(uuid4()),
            "option_id": "option-v1-x",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": code.value,
        "message": "Not enough memory.",
        "required_mib": 5000,
        "available_mib": 900,
    }
