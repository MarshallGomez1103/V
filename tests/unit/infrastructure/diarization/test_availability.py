"""Diarization availability: installed models AND the optional runtime."""

from __future__ import annotations

from typing import cast

import pytest

from voz.application.ports.diarization_availability import DiarizationAvailability
from voz.infrastructure.diarization.availability import SherpaDiarizationAvailability
from voz.infrastructure.diarization.models import DiarizationModelStore


class _Store:
    def __init__(self, installed: bool) -> None:
        self.installed = installed

    def is_installed(self) -> bool:
        return self.installed


@pytest.mark.parametrize(
    ("installed", "runtime", "expected"),
    [
        (True, True, True),
        (True, False, False),
        (False, True, False),
        (False, False, False),
    ],
)
def test_requires_models_and_runtime(
    installed: bool, runtime: bool, expected: bool
) -> None:
    availability = SherpaDiarizationAvailability(
        cast(DiarizationModelStore, _Store(installed)), has_runtime=lambda: runtime
    )

    assert isinstance(availability, DiarizationAvailability)
    assert availability.is_available() is expected
