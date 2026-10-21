"""Collected test ids stay usable on every CI runner."""

from __future__ import annotations

import pytest


def test_collected_test_ids_stay_short(request: pytest.FixtureRequest) -> None:
    # pytest exports each id as PYTEST_CURRENT_TEST (Windows caps a variable at
    # 32767 chars) and prints it in reports: give bulky parameters explicit ids.
    too_long = [
        item.nodeid[:80] for item in request.session.items if len(item.nodeid) > 10_000
    ]
    assert too_long == []
