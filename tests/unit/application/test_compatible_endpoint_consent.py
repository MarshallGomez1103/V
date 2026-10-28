"""Cloud consent belongs to a non-loopback URL; a local one records none."""

from __future__ import annotations

import pytest

from voz.application.ports.compatible_endpoints import consent_to_record


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.example.com/v1",
        "https://192.168.1.20:8443/v1",
        "https://localhost.example.com/v1",
    ],
)
def test_a_remote_server_keeps_the_consent_it_was_given(base_url: str) -> None:
    assert consent_to_record(True, base_url) is True
    assert consent_to_record(False, base_url) is False


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:8080/v1",
        "http://127.0.0.1:11434/v1",
        "http://[::1]:8000/v1",
        "  http://localhost:8080/v1 ",
    ],
)
def test_a_local_server_records_no_consent(base_url: str) -> None:
    assert consent_to_record(True, base_url) is False
    assert consent_to_record(False, base_url) is False


def test_an_unparsable_url_is_treated_as_remote() -> None:
    assert consent_to_record(True, "http://[") is True
