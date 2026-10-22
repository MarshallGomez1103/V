"""Speech synthesis engine that renders each chunk in a child process.

Native TTS runtimes hold the GIL and may crash; a child keeps the server's
interpreter free and turns any crash into a typed ``synthesis_failed``.
Cancellation and timeouts end the child (terminate, then kill). The child speaks
the pipe protocol of :mod:`voz.infrastructure.tts.protocol`.

ponytail: one child per ``synthesize`` call, so the model is reloaded for every
chunk (about a second for the small models). A persistent worker per model is
the next step only if a measurement shows it matters; it would need its own
lifecycle (idle shutdown, restart on crash, one request at a time).
"""

from __future__ import annotations

import contextlib
import os
import queue
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final

from voz.application.ports.speech_synthesis import (
    PcmAudio,
    SynthesisCancellationToken,
    SynthesisError,
    SynthesisFailureCode,
    SynthesisProgressCallback,
    SynthesisProviderInfo,
    SynthesisRequirements,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.synthesis_request import (
    MAX_SYNTHESIS_SPEED,
    MIN_SYNTHESIS_SPEED,
)
from voz.domain.entities.voice import Voice
from voz.infrastructure.child_env import child_environment
from voz.infrastructure.process_tree import kill_tree
from voz.infrastructure.tts.protocol import (
    AudioChunk,
    End,
    Progress,
    ProtocolError,
    WorkerError,
    WorkerRequest,
    encode_request,
    read_events,
)

_Code = SynthesisFailureCode
DEFAULT_TIMEOUT_SECONDS: Final = 120.0
_POLL_SECONDS: Final = 0.05
_TERMINATE_GRACE_SECONDS: Final = 0.5
_EXIT_WAIT_SECONDS: Final = 2.0
_MESSAGES: Final = {
    _Code.VOICE_NOT_FOUND: "The selected voice does not exist in this model.",
    _Code.MODEL_NOT_INSTALLED: "The selected model is not installed for this engine.",
    _Code.RUNTIME_UNAVAILABLE: "The speech synthesis runtime is not available.",
    _Code.SYNTHESIS_FAILED: "Speech synthesis failed.",
    _Code.CANCELLED: "Speech synthesis was cancelled.",
    _Code.TEXT_TOO_LONG: "The text chunk is longer than this engine accepts.",
}
# What a child may report; "cancelled" is ours alone, anything else is a failure.
_WORKER_CODES: Final = frozenset(
    {
        _Code.VOICE_NOT_FOUND,
        _Code.MODEL_NOT_INSTALLED,
        _Code.RUNTIME_UNAVAILABLE,
        _Code.TEXT_TOO_LONG,
    }
)


def default_tts_threads() -> int:
    """Cores for one synthesis: leave some for the server and the UI."""
    return min(4, max(1, (os.cpu_count() or 2) - 1))


@dataclass(frozen=True, slots=True)
class TtsModelManifest:
    """What the engine knows about one installed model (built by its catalog).

    ``files`` names the model files the worker needs (``{"model": path, ...}``);
    ``family`` tells the worker how to load them.
    """

    family: str
    files: Mapping[str, Path]
    voices: tuple[Voice, ...]
    languages: tuple[str, ...] = ()
    ram_bytes: int | None = None
    disk_bytes: int | None = None

    def __post_init__(self) -> None:
        if not self.family.strip():
            raise ValueError("family must be a non-blank string")
        if not self.voices:
            raise ValueError("a manifest needs at least one voice")
        if len({voice.id for voice in self.voices}) != len(self.voices):
            raise ValueError("voice ids must be unique")


type ManifestSource = (
    Mapping[str, TtsModelManifest] | Callable[[str], TtsModelManifest | None]
)
"""A frozen ``{model_id: manifest}`` or a live lookup by ``model_id``."""


def _error(code: SynthesisFailureCode) -> SynthesisError:
    return SynthesisError(code, _MESSAGES[code])


def _feed(stdin: IO[bytes], payload: bytes) -> None:
    try:
        stdin.write(payload)
        stdin.close()
    except OSError:  # the child died or was killed: the reader reports it
        pass


def _close_pipes(child: subprocess.Popen[bytes]) -> None:
    for stream in (child.stdin, child.stdout):
        if stream is not None:
            with contextlib.suppress(OSError):
                stream.close()


def _pump(stdout: IO[bytes], events: queue.Queue[object]) -> None:
    try:
        for event in read_events(stdout):
            events.put(event)
    except ProtocolError as error:
        events.put(error)
    except (OSError, ValueError):  # pipe closed under us
        pass
    finally:
        events.put(None)


class SubprocessSynthesisProvider:
    """``SpeechSynthesisProvider`` over a pipe-protocol child process.

    ``argv`` is the full child command (``[sys.executable, "-m", module]``);
    ``manifests`` maps ``ModelDescriptor.model_id`` to its installed files and
    voices: a mapping is copied once, a lookup callable (``store.manifest``) is
    asked on every call, so installs and deletes show up live. Safe to call
    from several threads: each call owns its child.
    """

    def __init__(
        self,
        *,
        info: SynthesisProviderInfo,
        argv: Sequence[str],
        manifests: ManifestSource,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        num_threads: int | None = None,
    ) -> None:
        if not argv:
            raise ValueError("argv must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._info = info
        self._argv = tuple(argv)
        self._lookup: Callable[[str], TtsModelManifest | None] = (
            manifests if callable(manifests) else dict(manifests).get
        )
        self._timeout = timeout_seconds
        self._threads = default_tts_threads() if num_threads is None else num_threads
        self._lock = threading.Lock()
        self._active: set[subprocess.Popen[bytes]] = set()
        self._closed = False

    # --- metadata ---------------------------------------------------------

    def describe(self) -> SynthesisProviderInfo:
        return self._info

    def voices(self, model: ModelDescriptor) -> tuple[Voice, ...]:
        return self._manifest(model).voices

    def languages(self, model: ModelDescriptor) -> tuple[str, ...]:
        return self._manifest(model).languages

    def requirements(self, model: ModelDescriptor) -> SynthesisRequirements:
        manifest = self._manifest(model)
        return SynthesisRequirements(
            runtime_ready=all(path.is_file() for path in manifest.files.values()),
            ram_bytes=manifest.ram_bytes,
            disk_bytes=manifest.disk_bytes,
        )

    def _manifest(self, model: ModelDescriptor) -> TtsModelManifest:
        manifest = self._lookup(model.model_id)
        if (
            model.provider_id != self._info.provider_id
            or not model.supports(ModelCapability.SYNTHESIS)
            or manifest is None
        ):
            raise _error(_Code.MODEL_NOT_INSTALLED)
        return manifest

    # --- synthesis --------------------------------------------------------

    def synthesize(
        self,
        chunk_text: str,
        *,
        model: ModelDescriptor,
        voice_id: str,
        speed: float = 1.0,
        cancellation: SynthesisCancellationToken | None = None,
        on_progress: SynthesisProgressCallback | None = None,
    ) -> PcmAudio:
        manifest = self._manifest(model)
        if not all(path.is_file() for path in manifest.files.values()):
            raise _error(_Code.MODEL_NOT_INSTALLED)
        _raise_if_cancelled(cancellation)
        text = chunk_text.strip()
        if not text:
            raise ValueError("chunk_text must not be blank")
        if len(text) > self._info.max_chunk_chars:
            raise _error(_Code.TEXT_TOO_LONG)
        if not MIN_SYNTHESIS_SPEED <= speed <= MAX_SYNTHESIS_SPEED:
            raise ValueError("speed is out of range")
        if voice_id not in {voice.id for voice in manifest.voices}:
            raise _error(_Code.VOICE_NOT_FOUND)
        request = WorkerRequest(
            family=manifest.family,
            files={name: str(path) for name, path in manifest.files.items()},
            voice_id=voice_id,
            speed=speed,
            text=text,
            num_threads=self._threads,
        )
        return self._run(request, cancellation, on_progress)

    def _run(
        self,
        request: WorkerRequest,
        cancellation: SynthesisCancellationToken | None,
        on_progress: SynthesisProgressCallback | None,
    ) -> PcmAudio:
        with self._lock:
            if self._closed:
                raise _error(_Code.RUNTIME_UNAVAILABLE)
            try:
                child = subprocess.Popen(
                    self._argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # Win
                    start_new_session=os.name != "nt",
                    env=child_environment(),
                )
            except OSError as error:
                raise _error(_Code.RUNTIME_UNAVAILABLE) from error
            self._active.add(child)
        assert child.stdin is not None and child.stdout is not None
        events: queue.Queue[object] = queue.Queue()
        reader = threading.Thread(target=_pump, args=(child.stdout, events))
        writer = threading.Thread(
            target=_feed, args=(child.stdin, encode_request(request))
        )
        reader.daemon = writer.daemon = True
        reader.start()
        writer.start()
        deadline = time.monotonic() + self._timeout
        audio: PcmAudio | None = None
        finished = False
        last = 0.0
        try:
            while True:
                _raise_if_cancelled(cancellation)
                if time.monotonic() > deadline:
                    raise _error(_Code.SYNTHESIS_FAILED)
                try:
                    item = events.get(timeout=_POLL_SECONDS)
                except queue.Empty:
                    continue
                if item is None or isinstance(item, ProtocolError):
                    break
                if isinstance(item, Progress):
                    if on_progress is not None and item.fraction >= last:
                        last = item.fraction
                        on_progress(last)
                elif isinstance(item, AudioChunk):
                    if audio is not None:  # one chunk, one audio record
                        break
                    audio = item.audio
                elif isinstance(item, WorkerError):
                    code = _Code(item.code) if item.code in _WORKER_CODES else None
                    raise _error(code or _Code.SYNTHESIS_FAILED)
                elif isinstance(item, End):
                    finished = True
                    break
            if finished:  # let it exit by itself; a lingering child is killed below
                with contextlib.suppress(subprocess.TimeoutExpired):
                    child.wait(timeout=_EXIT_WAIT_SECONDS)
        finally:
            self._stop(child)
            reader.join(timeout=1.0)  # EOF follows the child's death
            _close_pipes(child)
        if self._closed and not finished:
            raise _error(_Code.CANCELLED)
        # ponytail: a non-zero exit after END is a failure too; a worker whose
        # native teardown crashes should leave with os._exit(0) after flushing.
        if not finished or audio is None or child.returncode != 0:
            raise _error(_Code.SYNTHESIS_FAILED)
        if on_progress is not None and last < 1.0:
            on_progress(1.0)
        return audio

    def _stop(self, child: subprocess.Popen[bytes]) -> None:
        """Terminate, kill after a short grace, always reap; idempotent."""
        try:
            # terminate() would orphan the worker's own children
            kill_tree(child, _TERMINATE_GRACE_SECONDS)
        finally:
            with self._lock:
                self._active.discard(child)

    def close(self) -> None:
        """Stop in-flight children and refuse new work; calling again is a no-op."""
        with self._lock:
            self._closed = True
            children = tuple(self._active)
        for child in children:
            if child.poll() is None:
                child.terminate()


def _raise_if_cancelled(cancellation: SynthesisCancellationToken | None) -> None:
    if cancellation is not None and cancellation.is_cancelled():
        raise _error(_Code.CANCELLED)


__all__ = [
    "ManifestSource",
    "SubprocessSynthesisProvider",
    "TtsModelManifest",
    "default_tts_threads",
]
