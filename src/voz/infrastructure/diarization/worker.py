"""Child process that runs one sherpa-onnx diarization.

sherpa-onnx's native call keeps the GIL for minutes on a long recording (the
whole segmentation pass), which freezes the HTTP server, the live progress and
the cancel button. Running it here keeps the server's interpreter free.

Protocol, all on pipes: argv carries the model paths and settings; stdin carries
the float32 samples (little endian); stdout carries ``VOZ P <done> <total>``
progress lines, ``VOZ R <start> <end> <speaker>`` turns and a final ``VOZ END``.
Anything else on stdout (native logs) is ignored by the parent.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from voz.infrastructure.diarization.sherpa import SherpaEngine

PREFIX = "VOZ"


def main(argv: list[str]) -> int:
    segmentation, embedding, threads, num_clusters, threshold, count = argv
    import numpy

    raw = sys.stdin.buffer.read(int(count) * 4)
    samples = numpy.frombuffer(raw, dtype="<f4")
    engine = SherpaEngine(
        importlib.import_module("sherpa_onnx"),
        Path(segmentation),
        Path(embedding),
        int(threads),
    )

    def progress(done: int, total: int) -> int:
        print(PREFIX, "P", done, total, flush=True)
        return 0

    turns = engine.diarize(
        samples,
        num_clusters=int(num_clusters),
        threshold=float(threshold),
        progress=progress,
    )
    for turn in turns:
        print(PREFIX, "R", repr(turn.start), repr(turn.end), turn.speaker)
    print(PREFIX, "END", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
