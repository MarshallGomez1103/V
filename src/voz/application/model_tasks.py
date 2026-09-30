"""Background model install tasks: one heavy task at a time, with progress and cancel.

Tasks live in memory only. They are not durable on purpose: an interrupted
download is resumed by the store from its ``.part`` files when the user asks to
install again, so nothing is lost by forgetting the task itself.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from voz.application.ports.external_models import ExternalModelError
from voz.application.ports.model_installation import (
    CancelCheck,
    ModelFile,
    ModelInstallation,
    ModelInstallationError,
    ModelInstallationFailureCode,
    ProgressCallback,
)
from voz.domain.entities.model_descriptor import ModelDescriptor

_LOG = logging.getLogger(__name__)
_KEEP_FINISHED = 20
_ACTIVE = ("queued", "running")


class _CatalogEntry(Protocol):
    @property
    def descriptor(self) -> ModelDescriptor: ...
    @property
    def files(self) -> Sequence[ModelFile]: ...


class _Catalog(Protocol):
    def entries(self) -> Sequence[_CatalogEntry]: ...


class _Store(Protocol):
    def is_installed(self, descriptor: ModelDescriptor) -> bool: ...

    def download(
        self,
        descriptor: ModelDescriptor,
        files: Sequence[ModelFile],
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation: ...


class _ExternalImport(Protocol):
    def available(
        self, origin: str = "buzz"
    ) -> Sequence[tuple[ModelDescriptor, object]]:
        """Catalog models the origin already holds (candidate details are opaque)."""
        ...

    def execute(
        self,
        model_id: str,
        origin: str = "buzz",
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelInstallation: ...


class ModelTaskFailureCode:
    UNCONFIRMED = "model_install_unconfirmed"
    UNKNOWN_MODEL = "model_unknown"
    ALREADY_INSTALLED = "model_already_installed"
    EXTERNAL_NOT_FOUND = "external_model_not_found"
    TASK_NOT_FOUND = "model_task_not_found"
    TASK_TERMINAL = "model_task_terminal"
    FAILED = "model_task_failed"  # unexpected error while installing


class ModelTaskError(Exception):
    """Typed failure with a stable code and a path-free message."""

    def __init__(self, code: str, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


@dataclass(frozen=True, slots=True)
class ModelTaskView:
    """Immutable, path-free snapshot of a task."""

    id: str
    model_id: str
    method: str
    origin: str | None
    state: str  # queued | running | completed | failed | cancelled
    done_bytes: int
    total_bytes: int
    error_code: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class _Task:
    id: str
    descriptor: ModelDescriptor
    files: Sequence[ModelFile]
    method: str
    origin: str | None
    state: str
    total_bytes: int
    created_at: datetime
    updated_at: datetime
    done_bytes: int = 0
    error_code: str | None = None
    cancel_requested: bool = False

    def view(self) -> ModelTaskView:
        return ModelTaskView(
            id=self.id,
            model_id=self.descriptor.model_id,
            method=self.method,
            origin=self.origin,
            state=self.state,
            done_bytes=self.done_bytes,
            total_bytes=self.total_bytes,
            error_code=self.error_code,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ModelTaskRunner:
    """FIFO queue drained by a single worker thread (one heavy task at a time)."""

    def __init__(
        self,
        catalog: _Catalog,
        store: _Store,
        external: _ExternalImport,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._catalog = catalog
        self._store = store
        self._external = external
        self._clock = clock
        self._lock = threading.Condition()
        self._tasks: dict[str, _Task] = {}  # insertion order = creation order
        self._queue: deque[_Task] = deque()
        self._thread: threading.Thread | None = None
        self._stopped = False

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        """Start the worker once; ``enqueue`` also calls it, so it is optional."""
        with self._lock:
            if self._thread is not None or self._stopped:
                return
            self._thread = threading.Thread(
                target=self._work, name="voz-model-tasks", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        """Cancel everything pending and join the worker (for the app lifespan)."""
        with self._lock:
            self._stopped = True
            for task in self._queue:
                self._finish(task, "cancelled", None)
            self._queue.clear()
            for task in self._tasks.values():
                if task.state == "running":
                    task.cancel_requested = True
            self._lock.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join()

    # -- use cases ------------------------------------------------------------

    def enqueue(
        self,
        model_id: str,
        method: str,
        origin: str | None,
        *,
        confirm: bool,
    ) -> ModelTaskView:
        """Queue an install; an active task for the same model is returned as is."""
        if confirm is not True:
            raise ModelTaskError(
                ModelTaskFailureCode.UNCONFIRMED,
                "Installing a model must be confirmed explicitly.",
            )
        entry = next(
            (e for e in self._catalog.entries() if e.descriptor.model_id == model_id),
            None,
        )
        if entry is None:
            raise ModelTaskError(
                ModelTaskFailureCode.UNKNOWN_MODEL, "The model is not in the catalog."
            )
        with self._lock:
            active = next(
                (
                    t
                    for t in self._tasks.values()
                    if t.state in _ACTIVE and t.descriptor.model_id == model_id
                ),
                None,
            )
            if active is not None:
                return active.view()
        if self._store.is_installed(entry.descriptor):
            raise ModelTaskError(
                ModelTaskFailureCode.ALREADY_INSTALLED,
                "The model is already installed.",
            )
        if method == "import":
            origin = origin or "buzz"
            if not any(
                found == entry.descriptor
                for found, _ in self._external.available(origin)
            ):
                raise ModelTaskError(
                    ModelTaskFailureCode.EXTERNAL_NOT_FOUND,
                    "No compatible copy of this model was found to reuse.",
                )
        else:
            origin = None
        now = self._clock()
        task = _Task(
            id=uuid4().hex,
            descriptor=entry.descriptor,
            files=tuple(entry.files),
            method=method,
            origin=origin,
            state="queued",
            total_bytes=sum(f.size_bytes for f in entry.files),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            if self._stopped:
                raise ModelTaskError(
                    ModelTaskFailureCode.FAILED, "The model task runner is stopped."
                )
            self._tasks[task.id] = task
            self._queue.append(task)
            self._lock.notify()
        self.start()
        return task.view()

    def get(self, task_id: str) -> ModelTaskView:
        with self._lock:
            return self._find(task_id).view()

    def list_tasks(self) -> tuple[ModelTaskView, ...]:
        """Active tasks plus the most recent finished ones, oldest first."""
        with self._lock:
            return tuple(t.view() for t in self._tasks.values())

    def cancel(self, task_id: str) -> ModelTaskView:
        """Queued tasks end at once; a running one stops at its next poll."""
        with self._lock:
            task = self._find(task_id)
            if task.state not in _ACTIVE:
                raise ModelTaskError(
                    ModelTaskFailureCode.TASK_TERMINAL, "The task already finished."
                )
            if task.state == "queued":
                self._queue.remove(task)
                self._finish(task, "cancelled", None)
            else:
                task.cancel_requested = True
            return task.view()

    # -- internals ------------------------------------------------------------

    def _find(self, task_id: str) -> _Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise ModelTaskError(
                ModelTaskFailureCode.TASK_NOT_FOUND, "The model task does not exist."
            )
        return task

    def _finish(self, task: _Task, state: str, error_code: str | None) -> None:
        """Move to a terminal state and prune old ones (caller holds the lock)."""
        task.state = state
        task.error_code = error_code
        task.updated_at = self._clock()
        finished = [t.id for t in self._tasks.values() if t.state not in _ACTIVE]
        for stale in finished[: max(0, len(finished) - _KEEP_FINISHED)]:
            del self._tasks[stale]

    def _work(self) -> None:
        while True:
            with self._lock:
                while not self._queue and not self._stopped:
                    self._lock.wait()
                if self._stopped:
                    return
                task = self._queue.popleft()
                task.state = "running"
                task.updated_at = self._clock()
            self._run(task)

    def _run(self, task: _Task) -> None:
        def progress(done: int, total: int) -> None:
            with self._lock:
                task.done_bytes, task.total_bytes = done, total
                task.updated_at = self._clock()

        def cancelled() -> bool:
            return task.cancel_requested

        state, code = "completed", None
        try:
            if task.method == "import":
                self._external.execute(
                    task.descriptor.model_id,
                    task.origin or "buzz",
                    progress=progress,
                    cancelled=cancelled,
                )
            else:
                self._store.download(
                    task.descriptor, task.files, progress=progress, cancelled=cancelled
                )
        except ModelInstallationError as error:
            if error.code is ModelInstallationFailureCode.CANCELLED:
                state = "cancelled"
            else:
                state, code = "failed", error.code.value
        except ExternalModelError as error:
            state, code = "failed", error.code.value
        except Exception:  # the worker must survive any adapter bug
            _LOG.exception("model task crashed")
            state, code = "failed", ModelTaskFailureCode.FAILED
        with self._lock:
            if state == "completed":
                task.done_bytes = task.total_bytes
            self._finish(task, state, code)


__all__ = [
    "ModelTaskError",
    "ModelTaskFailureCode",
    "ModelTaskRunner",
    "ModelTaskView",
]
