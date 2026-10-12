"""Shared infrastructure guards."""

from __future__ import annotations

from uuid import uuid4

import pytest

from voz.infrastructure._payload import require_uuid


def test_require_uuid_accepts_uuid_and_rejects_strings() -> None:
    require_uuid(uuid4(), field="project_id")
    with pytest.raises(TypeError, match="project_id must be a UUID"):
        require_uuid(str(uuid4()), field="project_id")
