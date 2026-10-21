"""Trusted CPU ONNX ASR child; no downloaded code or native diagnostic output.

ponytail: non-overlapping 30-second windows bound native input. Words crossing
window boundaries may lose accuracy; alignment and overlap need measured models.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import wave
from array import array
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from voz.infrastructure.asr.sherpa_onnx_options import observed_language

MAX_WINDOW_FRAMES = 480_000
MAX_LINE_BYTES = 65_536


class Stream(Protocol):
    result: object

    def accept_waveform(self, sample_rate: int, waveform: Sequence[float]) -> None: ...


class Recognizer(Protocol):
    def create_stream(self) -> Stream: ...

    def decode_stream(self, stream: Stream) -> None: ...


class Factory(Protocol):
    def __call__(
        self,
        *,
        encoder: str,
        decoder: str,
        tokens: str,
        language: str,
        task: str,
        provider: str,
        num_threads: int,
        debug: bool,
        enable_token_timestamps: bool,
        enable_segment_timestamps: bool,
    ) -> Recognizer: ...


def load_whisper(
    files: Mapping[str, Path],
    language: str | None = None,
    *,
    factory: Factory | None = None,
) -> Recognizer:
    if factory is None:
        module = importlib.import_module("sherpa_onnx")
        factory = cast(Factory, module.OfflineRecognizer.from_whisper)
    return factory(
        encoder=str(files["encoder"]),
        decoder=str(files["decoder"]),
        tokens=str(files["tokens"]),
        language="" if language is None else language,
        task="transcribe",
        provider="cpu",
        num_threads=1,
        debug=False,
        enable_token_timestamps=False,
        enable_segment_timestamps=False,
    )


class TransducerFactory(Protocol):
    def __call__(
        self,
        *,
        encoder: str,
        decoder: str,
        joiner: str,
        tokens: str,
        provider: str,
        num_threads: int,
        debug: bool,
        decoding_method: str,
        model_type: str,
    ) -> Recognizer: ...


def load_nemo_transducer(
    files: Mapping[str, Path], *, factory: TransducerFactory | None = None
) -> Recognizer:
    if factory is None:
        module = importlib.import_module("sherpa_onnx")
        factory = cast(TransducerFactory, module.OfflineRecognizer.from_transducer)
    return factory(
        encoder=str(files["encoder"]),
        decoder=str(files["decoder"]),
        joiner=str(files["joiner"]),
        tokens=str(files["tokens"]),
        provider="cpu",
        num_threads=2,
        debug=False,
        decoding_method="greedy_search",
        model_type="nemo_transducer",
    )


def load_recognizer(
    family: str, files: Mapping[str, Path], language: str | None
) -> Recognizer:
    if family == "whisper":
        return load_whisper(files, language)
    if family == "nemo_transducer" and language is None:
        return load_nemo_transducer(files)
    raise ValueError("Unsupported ASR family or language hint")


def decode_audio(
    audio: Path,
    recognizer: Recognizer,
    *,
    emit: Callable[[dict[str, object]], None],
    start_ms: int = 0,
    end_ms: int | None = None,
) -> None:
    language: str | None = None
    conflicted = False
    with wave.open(str(audio), "rb") as source:
        if (
            source.getnchannels(),
            source.getsampwidth(),
            source.getframerate(),
            source.getcomptype(),
        ) != (1, 2, 16000, "NONE"):
            raise ValueError("Invalid normalized audio")
        stop = (
            source.getnframes()
            if end_ms is None
            else min(source.getnframes(), end_ms * 16)
        )
        position = start_ms * 16
        if position < 0 or position >= stop:
            raise ValueError("Empty audio clip")
        source.setpos(position)
        while position < stop:
            count = min(MAX_WINDOW_FRAMES, stop - position)
            block = source.readframes(count)
            if len(block) != count * 2:
                raise ValueError("Truncated audio")
            pcm = array("h")
            pcm.frombytes(block)
            if sys.byteorder != "little":
                pcm.byteswap()
            samples = array("f", (sample / 32768.0 for sample in pcm))
            stream = recognizer.create_stream()
            stream.accept_waveform(16000, samples)
            recognizer.decode_stream(stream)
            text = getattr(stream.result, "text", None)
            if not isinstance(text, str):
                raise ValueError("Invalid native result")
            observed = observed_language(getattr(stream.result, "lang", None))
            if observed is not None:
                if language is not None and observed != language:
                    conflicted = True
                language = observed
            if text:
                emit(
                    {
                        "type": "segment",
                        "start_ms": position // 16,
                        "end_ms": (position + count + 15) // 16,
                        "text": text,
                    }
                )
            position += count
            emit({"type": "progress", "position_ms": (position + 15) // 16})
    emit({"type": "end", "language": None if conflicted else language})


def main() -> int:
    result_fd = os.dup(sys.stdout.fileno())
    try:
        with open(os.devnull, "wb") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
            os.dup2(sink.fileno(), sys.stderr.fileno())
            request_path = Path(sys.argv[1])
            if request_path.stat().st_size > MAX_LINE_BYTES:
                return 1
            request = json.loads(request_path.read_text(encoding="utf-8"))
            files = {key: Path(value) for key, value in request["files"].items()}
            recognizer = load_recognizer(
                request.get("family", "whisper"), files, request["language"]
            )

            def emit(event: dict[str, object]) -> None:
                line = json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n"
                if len(line) > MAX_LINE_BYTES:
                    raise ValueError("Result too large")
                os.write(result_fd, line)

            decode_audio(
                Path(request["audio"]),
                recognizer,
                emit=emit,
                start_ms=request["start_ms"],
                end_ms=request["end_ms"],
            )
        return 0
    except Exception:
        return 1
    finally:
        os.close(result_fd)


if __name__ == "__main__":
    os._exit(main())
