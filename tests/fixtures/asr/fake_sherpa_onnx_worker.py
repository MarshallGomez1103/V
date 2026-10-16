"""Offline child fixture: canonical events, hangs and malformed output."""

import json
import os
import sys
import time
import wave
from pathlib import Path


def emit(value: object) -> None:
    print(json.dumps(value), flush=True)


def main() -> int:
    request = json.loads(Path(sys.argv[1]).read_text())
    mode = os.environ.get("FAKE_SHERPA_MODE", "normal")
    if mode in {"load", "native", "hang"}:
        marker = os.environ.get("FAKE_SHERPA_MARKER")
        if marker:
            Path(marker).write_text(str(os.getpid()))
        time.sleep(60)
    if mode == "crash":
        print("SECRET", file=sys.stderr)
        return 1
    if mode == "corrupt":
        print("SECRET not JSON", flush=True)
        return 0
    if mode == "oversized":
        print("x" * 100000, flush=True)
        return 0
    with wave.open(request["audio"], "rb") as source:
        stop = min(source.getnframes(), request["end_ms"] * 16)
    position = request["start_ms"] * 16
    index = 0
    while position < stop:
        end = min(position + 480000, stop)
        emit(
            {
                "type": "segment",
                "start_ms": -1 if mode == "bad-offset" else position // 16,
                "end_ms": (end + 15) // 16,
                "text": "hola mundo"
                if stop - position <= 480000 and index == 0
                else "hola"
                if index == 0
                else " mundo",
            }
        )
        emit({"type": "progress", "position_ms": (end + 15) // 16})
        position = end
        index += 1
    if mode != "missing-end":
        emit(
            {
                "type": "end",
                "language": None
                if mode == "no-language"
                else "SECRET/private"
                if mode == "unsafe-language"
                else "es",
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
