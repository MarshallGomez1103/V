"""Uploaded sources stay retained only while their independent copy is staged."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest

from voz.application.import_custom_model import ImportCustomModel
from voz.application.ports.custom_models import (
    CustomModelPlan,
    CustomModelPreview,
    CustomModelRequest,
    CustomValidation,
)
from voz.infrastructure.asr.catalog import faster_whisper_catalog


@pytest.mark.parametrize("failed", [False, True])
def test_source_context_covers_copy_and_releases_on_failure(
    tmp_path: Path, failed: bool
) -> None:
    descriptor = faster_whisper_catalog()[0].descriptor
    plan = CustomModelPlan(
        CustomModelPreview("a" * 32, descriptor, "ctranslate2", "unknown", 1, 1), ()
    )
    active = False
    released = False

    @contextmanager
    def retain(value: CustomModelPlan) -> Generator[None]:
        nonlocal active, released
        assert value is plan
        active = True
        try:
            yield
        finally:
            active = False
            released = True

    def copy(*_args: object, **_kwargs: object) -> Path:
        assert active
        if failed:
            raise OSError("fixture copy failed")
        return tmp_path

    def validate(*_args: object, **_kwargs: object) -> CustomValidation:
        assert released and not active
        return CustomValidation()

    backend = Mock()
    backend.prepare.return_value = plan
    backend.stage.side_effect = copy
    backend.publish.return_value = descriptor
    validator = Mock()
    validator.validate.side_effect = validate
    importer = ImportCustomModel(backend, validator, staging_context=retain)
    importer.prepare(
        CustomModelRequest("folder", "source", "faster-whisper", "ctranslate2", "Test")
    )
    if failed:
        with pytest.raises(OSError):
            importer.execute(plan.preview.id, confirm=True)
        validator.validate.assert_not_called()
        backend.publish.assert_not_called()
    else:
        assert importer.execute(plan.preview.id, confirm=True) is descriptor
        backend.discard.assert_called_once_with(tmp_path)
    assert released and not active
