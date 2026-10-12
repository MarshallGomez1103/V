"""ComputeSlot: one heavy job at a time, FIFO, cancellable while waiting."""

from __future__ import annotations

import threading
import time
from uuid import uuid4

import pytest

from voz.application.compute_slot import (
    ComputeKind,
    ComputeSlot,
    SlotUser,
    SlotWaitCancelled,
)


class _Flag:
    def __init__(self) -> None:
        self.event = threading.Event()

    def is_cancelled(self) -> bool:
        return self.event.is_set()


def _wait_until(condition: object, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if callable(condition) and condition():
            return
        time.sleep(0.005)
    raise AssertionError("condition not met in time")


def test_reports_who_holds_the_slot_and_frees_it_after() -> None:
    slot = ComputeSlot()
    job_id = uuid4()
    assert slot.holder() is None

    with slot.hold(ComputeKind.SYNTHESIS, job_id):
        assert slot.holder() == SlotUser(ComputeKind.SYNTHESIS, job_id)

    assert slot.holder() is None
    assert slot.waiting() == ()


def test_slot_is_freed_when_the_body_raises() -> None:
    slot = ComputeSlot()

    with (
        pytest.raises(RuntimeError),
        slot.hold(ComputeKind.TRANSCRIPTION, uuid4()),
    ):
        raise RuntimeError("boom")

    assert slot.holder() is None


def test_mutual_exclusion_across_threads() -> None:
    slot = ComputeSlot()
    inside = 0
    peak = 0
    guard = threading.Lock()

    def work() -> None:
        nonlocal inside, peak
        with slot.hold(ComputeKind.SYNTHESIS, uuid4()):
            with guard:
                inside += 1
                peak = max(peak, inside)
            time.sleep(0.005)
            with guard:
                inside -= 1

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert peak == 1
    assert slot.holder() is None


def test_waiters_are_served_in_arrival_order_and_listed() -> None:
    slot = ComputeSlot()
    order: list[int] = []
    release = threading.Event()
    first = uuid4()
    ids = [uuid4() for _ in range(3)]

    def holder() -> None:
        with slot.hold(ComputeKind.TRANSCRIPTION, first):
            release.wait(5)

    def waiter(index: int) -> None:
        with slot.hold(ComputeKind.SYNTHESIS, ids[index]):
            order.append(index)

    blocker = threading.Thread(target=holder)
    blocker.start()
    _wait_until(lambda: slot.holder() is not None)
    waiters: list[threading.Thread] = []
    for index in range(3):
        thread = threading.Thread(target=waiter, args=(index,))
        thread.start()
        waiters.append(thread)
        _wait_until(lambda index=index: len(slot.waiting()) == index + 1)

    assert slot.holder() == SlotUser(ComputeKind.TRANSCRIPTION, first)
    assert slot.waiting() == tuple(SlotUser(ComputeKind.SYNTHESIS, i) for i in ids)

    release.set()
    for thread in (blocker, *waiters):
        thread.join(5)
    assert order == [0, 1, 2]


def test_cancelled_waiter_leaves_without_running_and_keeps_the_line() -> None:
    slot = ComputeSlot()
    release = threading.Event()
    cancelled = _Flag()
    ran: list[str] = []
    outcome: list[str] = []
    victim, after = uuid4(), uuid4()

    def holder() -> None:
        with slot.hold(ComputeKind.TRANSCRIPTION, uuid4()):
            release.wait(5)

    def doomed() -> None:
        try:
            with slot.hold(ComputeKind.SYNTHESIS, victim, cancellation=cancelled):
                ran.append("doomed")
        except SlotWaitCancelled:
            outcome.append("left")

    def next_in_line() -> None:
        with slot.hold(ComputeKind.SYNTHESIS, after):
            ran.append("after")

    threads = [threading.Thread(target=holder)]
    threads[0].start()
    _wait_until(lambda: slot.holder() is not None)
    for target in (doomed, next_in_line):
        thread = threading.Thread(target=target)
        thread.start()
        threads.append(thread)
        expected = len(threads) - 1
        _wait_until(lambda n=expected: len(slot.waiting()) == n)

    cancelled.event.set()
    _wait_until(lambda: outcome == ["left"])
    assert slot.waiting() == (SlotUser(ComputeKind.SYNTHESIS, after),)

    release.set()
    for thread in threads:
        thread.join(5)
    assert ran == ["after"]
    assert slot.holder() is None


def test_already_cancelled_job_does_not_wait_or_run_when_slot_is_busy() -> None:
    slot = ComputeSlot()
    cancelled = _Flag()
    cancelled.event.set()

    with slot.hold(ComputeKind.TRANSCRIPTION, uuid4()):
        with (
            pytest.raises(SlotWaitCancelled),
            slot.hold(ComputeKind.SYNTHESIS, uuid4(), cancellation=cancelled),
        ):
            pytest.fail("must not run")
        assert slot.waiting() == ()
