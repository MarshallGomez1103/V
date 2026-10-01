"""ModelTaskRunner with fake ports: progress, cancel, failure, dedupe, FIFO, stop."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

import pytest

from voz.application.model_tasks import (
    ModelTaskError,
    ModelTaskRunner,
    ModelTaskView,
)
from voz.application.ports.external_models import (
    ExternalModelError,
    ExternalModelFailureCode,
)
from voz.application.ports.model_installation import (
    CancelCheck,
    ModelFile,
    ModelInstallation,
    ModelInstallationError,
    ModelInstallationFailureCode,
    ProgressCallback,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor

NOW = datetime(2026, 9, 30, 10, tzinfo=UTC)


def make(model_id: str) -> ModelDescriptor:
    return ModelDescriptor(
        provider_id="faster-whisper",
        model_id=model_id,
        display_name=model_id.title(),
        capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
        source=f"publisher/{model_id}",
        revision="a" * 40,
    )


@dataclass(frozen=True)
class Entry:
    descriptor: ModelDescriptor
    files: tuple[ModelFile, ...]


class Catalog:
    def __init__(self, *ids: str) -> None:
        self._entries = tuple(
            Entry(make(i), (ModelFile("model.bin", 100, None),)) for i in ids
        )

    def entries(self) -> tuple[Entry, ...]:
        return self._entries


@dataclass
class Store:
    """``download`` blocks on a gate so tests can observe the running state."""

    installed: set[str] = field(default_factory=lambda: set[str]())
    gate: threading.Event = field(default_factory=threading.Event)
    started: threading.Event = field(default_factory=threading.Event)
    order: list[str] = field(default_factory=lambda: list[str]())
    fail: ModelInstallationError | Exception | None = None
    honour_cancel: bool = True

    def is_installed(self, descriptor: ModelDescriptor) -> bool:
        return descriptor.model_id in self.installed

    def download(
        self,
        descriptor: ModelDescriptor,
        files: Sequence[ModelFile],
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation:
        self.order.append(descriptor.model_id)
        total = sum(f.size_bytes for f in files)
        if progress:
            progress(40, total)
        self.started.set()
        while not self.gate.wait(0.005):
            if self.honour_cancel and cancelled is not None and cancelled():
                raise ModelInstallationError(
                    ModelInstallationFailureCode.CANCELLED, "cancelled"
                )
        if self.fail is not None:
            raise self.fail
        self.installed.add(descriptor.model_id)
        return ModelInstallation(descriptor, NOW)


class External:
    def __init__(self, *ids: str) -> None:
        self.ids = set(ids)
        self.calls: list[tuple[str, str]] = []

    def available(
        self, origin: str = "buzz"
    ) -> tuple[tuple[ModelDescriptor, str], ...]:
        return tuple((make(i), origin) for i in sorted(self.ids))

    def execute(
        self,
        model_id: str,
        origin: str = "buzz",
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation:
        del cancelled
        self.calls.append((model_id, origin))
        if progress:
            progress(100, 100)
        return ModelInstallation(make(model_id), NOW)


def wait_for(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.005)


@pytest.fixture
def store() -> Store:
    return Store()


@pytest.fixture
def runner(store: Store) -> Iterator[ModelTaskRunner]:
    instance = ModelTaskRunner(
        Catalog("tiny", "base", "small"), store, External("small")
    )
    yield instance
    store.gate.set()
    instance.stop()


def state_of(runner: ModelTaskRunner, view: ModelTaskView) -> str:
    return runner.get(view.id).state


def test_download_reports_progress_and_completes(
    runner: ModelTaskRunner, store: Store
) -> None:
    view = runner.enqueue("tiny", "download", None, confirm=True)
    assert (view.state, view.done_bytes, view.total_bytes) == ("queued", 0, 100)
    assert (view.method, view.origin, view.error_code) == ("download", None, None)

    assert store.started.wait(5)
    wait_for(lambda: runner.get(view.id).done_bytes == 40)
    assert state_of(runner, view) == "running"

    store.gate.set()
    wait_for(lambda: state_of(runner, view) == "completed")
    done = runner.get(view.id)
    assert (done.done_bytes, done.total_bytes, done.error_code) == (100, 100, None)
    assert done.updated_at >= done.created_at


def test_confirm_is_required_and_nothing_is_queued(
    runner: ModelTaskRunner, store: Store
) -> None:
    with pytest.raises(ModelTaskError) as raised:
        runner.enqueue("tiny", "download", None, confirm=False)
    assert raised.value.code == "model_install_unconfirmed"
    assert runner.list_tasks() == () and store.order == []


def test_unknown_and_installed_models_are_rejected(
    runner: ModelTaskRunner, store: Store
) -> None:
    with pytest.raises(ModelTaskError) as unknown:
        runner.enqueue("nope", "download", None, confirm=True)
    assert unknown.value.code == "model_unknown"
    store.installed.add("tiny")
    with pytest.raises(ModelTaskError) as installed:
        runner.enqueue("tiny", "download", None, confirm=True)
    assert installed.value.code == "model_already_installed"


def test_import_requires_a_candidate_and_runs_through_the_importer(
    store: Store,
) -> None:
    external = External("small")
    runner = ModelTaskRunner(Catalog("tiny", "small"), store, external)
    try:
        with pytest.raises(ModelTaskError) as raised:
            runner.enqueue("tiny", "import", "buzz", confirm=True)
        assert raised.value.code == "external_model_not_found"

        view = runner.enqueue("small", "import", "buzz", confirm=True)
        assert view.method == "import" and view.origin == "buzz"
        wait_for(lambda: runner.get(view.id).state == "completed")
        assert external.calls == [("small", "buzz")] and store.order == []
    finally:
        runner.stop()


def test_failure_keeps_a_stable_code(runner: ModelTaskRunner, store: Store) -> None:
    store.fail = ModelInstallationError(
        ModelInstallationFailureCode.CHECKSUM_MISMATCH, "bad"
    )
    store.gate.set()
    view = runner.enqueue("tiny", "download", None, confirm=True)
    wait_for(lambda: state_of(runner, view) == "failed")
    assert runner.get(view.id).error_code == "model_installation_checksum_mismatch"


def test_import_failure_and_unexpected_error_codes(store: Store) -> None:
    class Broken(External):
        def execute(self, model_id: str, origin: str = "buzz", **_: object):  # type: ignore[override]
            raise ExternalModelError(ExternalModelFailureCode.NOT_FOUND, "gone")

    runner = ModelTaskRunner(Catalog("tiny", "small"), store, Broken("small"))
    try:
        view = runner.enqueue("small", "import", None, confirm=True)
        wait_for(lambda: runner.get(view.id).state == "failed")
        assert runner.get(view.id).error_code == "external_model_not_found"

        store.fail = RuntimeError("secret /home/host/path")
        store.gate.set()
        crash = runner.enqueue("tiny", "download", None, confirm=True)
        wait_for(lambda: runner.get(crash.id).state == "failed")
        assert runner.get(crash.id).error_code == "model_task_failed"
    finally:
        runner.stop()


def test_cancel_running_task_stops_cooperatively(
    runner: ModelTaskRunner, store: Store
) -> None:
    view = runner.enqueue("tiny", "download", None, confirm=True)
    assert store.started.wait(5)

    runner.cancel(view.id)
    wait_for(lambda: state_of(runner, view) == "cancelled")
    assert runner.get(view.id).error_code is None
    with pytest.raises(ModelTaskError) as raised:
        runner.cancel(view.id)
    assert raised.value.code == "model_task_terminal"


def test_cancel_queued_task_never_starts(runner: ModelTaskRunner, store: Store) -> None:
    first = runner.enqueue("tiny", "download", None, confirm=True)
    second = runner.enqueue("base", "download", None, confirm=True)
    assert store.started.wait(5)

    assert runner.cancel(second.id).state == "cancelled"
    store.gate.set()
    wait_for(lambda: state_of(runner, first) == "completed")
    assert store.order == ["tiny"]


def test_duplicate_enqueue_returns_the_active_task(
    runner: ModelTaskRunner, store: Store
) -> None:
    first = runner.enqueue("tiny", "download", None, confirm=True)
    again = runner.enqueue("tiny", "download", None, confirm=True)
    assert again.id == first.id
    assert len(runner.list_tasks()) == 1

    store.gate.set()
    wait_for(lambda: state_of(runner, first) == "completed")
    store.installed.clear()  # removed later: a new install is a new task
    assert runner.enqueue("tiny", "download", None, confirm=True).id != first.id


def test_tasks_run_fifo_one_at_a_time(runner: ModelTaskRunner, store: Store) -> None:
    views = [
        runner.enqueue(model, "download", None, confirm=True)
        for model in ("tiny", "base", "small")
    ]
    assert store.started.wait(5)
    time.sleep(0.05)
    assert store.order == ["tiny"]  # the others wait their turn
    assert [state_of(runner, v) for v in views] == ["running", "queued", "queued"]

    store.gate.set()
    wait_for(lambda: all(state_of(runner, v) == "completed" for v in views))
    assert store.order == ["tiny", "base", "small"]


def test_unknown_task_and_finished_history_is_bounded(
    runner: ModelTaskRunner, store: Store
) -> None:
    with pytest.raises(ModelTaskError) as raised:
        runner.get("missing")
    assert raised.value.code == "model_task_not_found"

    store.gate.set()
    first = runner.enqueue("tiny", "download", None, confirm=True)
    wait_for(lambda: state_of(runner, first) == "completed")
    for _ in range(25):
        store.installed.clear()
        done = runner.enqueue("tiny", "download", None, confirm=True)
        wait_for(lambda task=done: state_of(runner, task) == "completed")
    assert len(runner.list_tasks()) == 20
    with pytest.raises(ModelTaskError):
        runner.get(first.id)


def test_stop_cancels_running_and_queued_and_joins(
    runner: ModelTaskRunner, store: Store
) -> None:
    running = runner.enqueue("tiny", "download", None, confirm=True)
    queued = runner.enqueue("base", "download", None, confirm=True)
    assert store.started.wait(5)

    runner.stop()

    assert state_of(runner, running) == "cancelled"
    assert state_of(runner, queued) == "cancelled"
    assert store.order == ["tiny"]
    assert not any(t.name == "voz-model-tasks" for t in threading.enumerate())
    with pytest.raises(ModelTaskError):
        runner.enqueue("small", "download", None, confirm=True)


def test_same_model_id_in_two_providers_is_told_apart_by_key() -> None:
    cpp = replace(make("small"), provider_id="whisper-cpp")

    class Both:
        def entries(self) -> tuple[Entry, ...]:
            files = (ModelFile("model.bin", 100, None),)
            return (Entry(make("small"), files), Entry(cpp, files))

    store = Store()
    instance = ModelTaskRunner(Both(), store, External())
    try:
        first = instance.enqueue("small", "download", None, confirm=True)
        second = instance.enqueue("whisper-cpp:small", "download", None, confirm=True)
        assert (first.key, second.key) == ("faster-whisper:small", "whisper-cpp:small")
        assert first.id != second.id
        # A bare id and its full key are the same model: the active task is reused.
        again = instance.enqueue("faster-whisper:small", "download", None, confirm=True)
        assert again.id == first.id
    finally:
        store.gate.set()
        instance.stop()
