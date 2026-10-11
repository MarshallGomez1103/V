from __future__ import annotations

from voz.interfaces.api.errors import api_error


def test_api_error_builds_stable_detail_body() -> None:
    error = api_error(404, "job_not_found", "The job does not exist.")

    assert error.status_code == 404
    assert error.detail == {
        "code": "job_not_found",
        "message": "The job does not exist.",
    }


def test_api_error_merges_extra_fields_without_overriding_core_ones() -> None:
    error = api_error(409, "conflict", "Nope.", job_id="j1", retry=False)

    assert error.status_code == 409
    assert error.detail == {
        "code": "conflict",
        "message": "Nope.",
        "job_id": "j1",
        "retry": False,
    }
