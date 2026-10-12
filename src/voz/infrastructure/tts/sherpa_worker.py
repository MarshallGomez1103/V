"""Child process that renders one TTS chunk with sherpa-onnx ``OfflineTts``.

Run as ``python -m voz.infrastructure.tts.sherpa_worker``; it speaks the pipe
protocol of :mod:`voz.infrastructure.tts.protocol` (one JSON request on stdin;
``V P``/``V A``/``V END``/``V ERR`` on stdout). The only module that imports
``sherpa_onnx`` for TTS, and only lazily while rendering.

Cancellation: the parent terminates this process (default SIGTERM handling
ends it even inside native code). If the parent dies, the next progress write
fails and the native callback returns non-zero, which stops generation. stdin
is closed by the parent right after the request, so EOF there means nothing.
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Final

from voz.application.ports.speech_synthesis import (
    PcmAudio,
    PcmSampleFormat,
    SynthesisFailureCode,
)
from voz.infrastructure.tts import families, protocol

_Code = SynthesisFailureCode
MAX_NUM_SENTENCES: Final = 1  # V4-01: measured setting; progress per sentence
_CONTINUE: Final = 1
_STOP: Final = 0


class WorkerFailure(Exception):
    def __init__(self, code: SynthesisFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def _emit(data: bytes) -> None:
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def _render(request: protocol.WorkerRequest) -> PcmAudio:
    try:
        metadata = families.read_onnx_metadata(
            families.metadata_model_path(request.files)
        )
    except (OSError, families.ModelFilesError) as error:
        raise WorkerFailure(_Code.MODEL_NOT_INSTALLED, str(error)) from error
    names = families.speaker_names(metadata)
    sid = families.resolve_sid(
        request.voice_id, names, families.speaker_count(metadata)
    )
    if sid is None:
        raise WorkerFailure(_Code.VOICE_NOT_FOUND, "unknown voice")
    family = families.canonical_family(request.family)
    lang = families.kokoro_lang(names[sid]) if sid < len(names) else ""
    try:
        spec = families.model_config(family, request.files, lang=lang)
    except families.ModelFilesError as error:
        raise WorkerFailure(_Code.MODEL_NOT_INSTALLED, str(error)) from error
    try:
        sherpa: Any = importlib.import_module("sherpa_onnx")
    except ImportError as error:
        raise WorkerFailure(_Code.RUNTIME_UNAVAILABLE, "sherpa-onnx missing") from error
    family_config = getattr(sherpa, spec.config_class)(**spec.kwargs)
    config = sherpa.OfflineTtsConfig(
        model=sherpa.OfflineTtsModelConfig(
            **{spec.field: family_config},
            num_threads=request.num_threads,
            provider="cpu",
        ),
        max_num_sentences=MAX_NUM_SENTENCES,
    )
    if not config.validate():
        raise WorkerFailure(_Code.MODEL_NOT_INSTALLED, "invalid model configuration")
    try:
        tts = sherpa.OfflineTts(config)
    except Exception as error:  # native loader: corrupt or foreign weights
        raise WorkerFailure(_Code.MODEL_NOT_INSTALLED, "cannot load model") from error
    if sid >= tts.num_speakers:
        raise WorkerFailure(_Code.VOICE_NOT_FOUND, "unknown voice")

    # sherpa-onnx 1.13.8 continues while the callback returns non-zero and
    # stops on 0, the opposite of its docstring (measured: returning 0 kept
    # only the first sentence).
    def on_chunk(_samples: object, progress: float) -> int:
        try:
            _emit(protocol.encode_progress(float(progress)))
        except (OSError, ValueError):  # the parent is gone: stop generating
            return _STOP
        return _CONTINUE

    generated = tts.generate(
        request.text, sid=sid, speed=request.speed, callback=on_chunk
    )
    import numpy

    samples = numpy.asarray(generated.samples, dtype="<f4").tobytes()
    if not samples:
        raise WorkerFailure(_Code.SYNTHESIS_FAILED, "the model produced no audio")
    return PcmAudio(samples, int(generated.sample_rate), PcmSampleFormat.FLOAT32)


def main() -> int:
    try:
        request = protocol.decode_request(sys.stdin.buffer.readline())
        audio = _render(request)
        _emit(protocol.encode_audio(audio))
        _emit(protocol.encode_end())
    except WorkerFailure as failure:
        _emit(protocol.encode_error(failure.code.value, str(failure)))
    except families.ModelFilesError as error:
        _emit(protocol.encode_error(_Code.MODEL_NOT_INSTALLED.value, str(error)))
    except Exception as error:
        _emit(protocol.encode_error(_Code.SYNTHESIS_FAILED.value, type(error).__name__))
    return 0


if __name__ == "__main__":
    status = main()
    sys.stdout.flush()
    # Skip native teardown: onnxruntime/espeak destructors may crash at exit,
    # which the parent would read as a failure after a complete chunk.
    os._exit(status)
