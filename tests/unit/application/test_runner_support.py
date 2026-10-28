"""Primitives the two job runners share."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from voz.application.runner_support import AnyEventToken, not_before

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_token_is_cancelled_when_any_of_its_events_is_set() -> None:
    cancel, stopping = threading.Event(), threading.Event()
    token = AnyEventToken((cancel, stopping))

    assert not token.is_cancelled()
    stopping.set()
    assert token.is_cancelled()
    stopping.clear()
    cancel.set()
    assert token.is_cancelled()


def test_token_without_events_is_never_cancelled() -> None:
    assert not AnyEventToken(()).is_cancelled()


def test_not_before_never_goes_back_in_time() -> None:
    assert not_before(_NOW, _NOW + timedelta(seconds=5)) == _NOW + timedelta(seconds=5)
    assert not_before(_NOW, _NOW - timedelta(seconds=5)) == _NOW
    assert not_before(_NOW, _NOW) == _NOW
