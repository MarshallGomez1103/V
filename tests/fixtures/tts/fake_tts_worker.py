"""Fake TTS worker speaking the VOZ pipe protocol (``voz.infrastructure.tts.protocol``).

Run as ``python fake_tts_worker.py``: one JSON request line on stdin, protocol
records on stdout. Deterministic int16 PCM at 16 kHz (a ramp whose length grows
with the text and shrinks with the speed). Behaviour switches live in the text:

``@crash``      exit 1 half way, no END      ``@exit3``    END, then exit 3
``@noend``      audio, then exit 0 w/o END   ``@err=CODE`` ERR with a path in text
``@garbage``    junk lines interleaved       ``@truncate`` promise more PCM than sent
``@slow``       progress forever (30 s)      ``@stubborn`` like @slow, ignores SIGTERM
``@twice``      two audio records            ``@badheader`` malformed audio header

If ``files`` has a ``pid_out`` entry the worker writes its pid there first.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from array import array
from pathlib import Path

from voz.application.ports.speech_synthesis import PcmAudio
from voz.infrastructure.tts import protocol

SAMPLE_RATE = 16_000
BLOCKS = 5


def pcm(text: str, voice_id: str, speed: float) -> bytes:
    frames = max(1_600, round(len(text) * 960 / speed))
    step = sum(voice_id.encode()) % 7 + 1
    samples = array("h", ((i * step) % 2_000 - 1_000 for i in range(frames)))
    if sys.byteorder == "big":
        samples.byteswap()
    return samples.tobytes()


def emit(data: bytes) -> None:
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def main() -> int:
    request = protocol.decode_request(sys.stdin.buffer.readline())
    pid_out = request.files.get("pid_out")
    if pid_out:
        Path(pid_out).write_text(str(os.getpid()))
    text = request.text
    if "@stubborn" in text:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if "@slow" in text or "@stubborn" in text:
        emit(protocol.encode_progress(0.1))
        time.sleep(30)
        return 0
    noisy = "@garbage" in text
    if noisy:
        emit(b"onnxruntime: loading model\n\xff\xfe binary \x00 junk\nV\nV X what\n")
        emit(b"V P not-a-number\nV END extra\nV ERR\n")
    if "@err=" in text:
        code = text.split("@err=", 1)[1].split()[0]
        emit(
            protocol.encode_error(
                code, "failed reading /home/someone/secret/model.onnx"
            )
        )
        return 0
    audio = PcmAudio(pcm(text, request.voice_id, request.speed), SAMPLE_RATE)
    if "@badheader" in text:
        emit(b"V A twelve 16000 int16\n")
        return 0
    size = len(audio.samples)
    for block in range(1, BLOCKS + 1):
        emit(protocol.encode_progress(block / BLOCKS))
        if noisy:
            emit(b"V P 0.001\nlog: block done\n")  # lower value: parent keeps monotone
        if "@crash" in text and block == 3:
            return 1
    if "@truncate" in text:
        emit(f"V A {size + 100} {SAMPLE_RATE} int16\n".encode() + audio.samples)
        return 0
    emit(protocol.encode_audio(audio))
    if "@twice" in text:
        emit(protocol.encode_audio(audio))
    if "@noend" in text:
        return 0
    emit(protocol.encode_end())
    return 3 if "@exit3" in text else 0


if __name__ == "__main__":
    raise SystemExit(main())
