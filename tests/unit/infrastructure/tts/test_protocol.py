"""Pure encoding/decoding of the TTS child-process pipe protocol."""

from __future__ import annotations

import io
import json

import pytest

from voz.application.ports.speech_synthesis import PcmAudio, PcmSampleFormat
from voz.infrastructure.tts import protocol
from voz.infrastructure.tts.protocol import (
    AudioChunk,
    End,
    Progress,
    ProtocolError,
    WorkerError,
    WorkerRequest,
)


def events(data: bytes) -> list[protocol.WorkerEvent]:
    return list(protocol.read_events(io.BytesIO(data)))


def request(**overrides: object) -> WorkerRequest:
    fields: dict[str, object] = {
        "family": "kitten",
        "files": {"model": "/m/model.onnx", "voices": "/m/voices.bin"},
        "voice_id": "3",
        "speed": 1.25,
        "text": "Hola mundo",
        "num_threads": 2,
    }
    return WorkerRequest(**{**fields, **overrides})  # type: ignore[arg-type]


def test_request_round_trips_on_exactly_one_line() -> None:
    nasty = 'línea 1\nlínea 2\r\n"V END"\nV A 4 16000 int16 \u2028 \x00'
    original = request(text=nasty)

    line = protocol.encode_request(original)

    assert line.endswith(b"\n") and line.count(b"\n") == 1
    assert line.isascii()
    assert protocol.decode_request(line) == original


def test_user_text_is_data_never_a_record() -> None:
    line = protocol.encode_request(request(text="V END\nV ERR boom\nV P 1"))

    assert events(line) == []  # even misread as a response it is just noise


@pytest.mark.parametrize(
    "mutation",
    [
        {"family": " "},
        {"family": 3},
        {"files": ["a"]},
        {"files": {"model": 1}},
        {"voice_id": ""},
        {"speed": 0},
        {"speed": -1.0},
        {"speed": True},
        {"speed": "1"},
        {"text": "  "},
        {"num_threads": 0},
        {"num_threads": 1.5},
        {"num_threads": True},
    ],
)
def test_decode_request_rejects_invalid_fields(mutation: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "family": "kitten",
        "files": {},
        "voice_id": "0",
        "speed": 1.0,
        "text": "x",
        "num_threads": 1,
        **mutation,
    }

    with pytest.raises(ProtocolError):
        protocol.decode_request(json.dumps(payload))


@pytest.mark.parametrize("line", [b"", b"not json", b"[1]", b'"x"', b"\xff\xfe"])
def test_decode_request_rejects_non_objects(line: bytes) -> None:
    with pytest.raises(ProtocolError):
        protocol.decode_request(line)


def test_decode_request_rejects_nan_speed() -> None:
    with pytest.raises(ProtocolError):
        protocol.decode_request(
            '{"family":"k","files":{},"voice_id":"0","speed":NaN,"text":"x",'
            '"num_threads":1}'
        )


def test_encode_helpers_produce_the_documented_records() -> None:
    assert protocol.encode_progress(0.5) == b"V P 0.500000\n"
    assert protocol.encode_progress(7) == b"V P 1.000000\n"
    assert protocol.encode_end() == b"V END\n"
    assert protocol.encode_error("synthesis_failed") == b"V ERR synthesis_failed\n"
    audio = PcmAudio(b"\x01\x00\x02\x00", 22_050)
    assert protocol.encode_audio(audio) == b"V A 4 22050 int16\n\x01\x00\x02\x00"
    with pytest.raises(ValueError, match="identifier"):
        protocol.encode_error("Bad Code")


def test_full_response_round_trips() -> None:
    audio = PcmAudio(bytes(range(64)) * 2, 24_000, PcmSampleFormat.FLOAT32)
    stream = (
        protocol.encode_progress(0.25)
        + protocol.encode_progress(1.0)
        + protocol.encode_audio(audio)
        + protocol.encode_end()
    )

    assert events(stream) == [Progress(0.25), Progress(1.0), AudioChunk(audio), End()]


def test_pcm_is_read_by_exact_length_even_if_it_looks_like_records() -> None:
    samples = (b"\nV END\nV ERR x y\n" + b"V P 0.5\n").ljust(32, b"\n")
    audio = PcmAudio(samples, 16_000)

    assert events(protocol.encode_audio(audio) + protocol.encode_end()) == [
        AudioChunk(audio),
        End(),
    ]


def test_foreign_and_malformed_lines_are_ignored() -> None:
    noise = (
        b"onnxruntime: loading\n\xff\xfe\x00 junk\n\n   \nV\nV X what\n"
        b"V P nope\nV P inf\nV P 0.1 0.2\nV END extra\nV ERR\nV ERR Bad code\n"
        b"W P 0.5\n"
    )

    assert events(noise + protocol.encode_progress(0.5) + protocol.encode_end()) == [
        Progress(0.5),
        End(),
    ]


def test_progress_is_clamped_to_the_unit_interval() -> None:
    assert events(b"V P 7\nV P -3\n") == [Progress(1.0), Progress(0.0)]


def test_overlong_foreign_line_is_dropped_without_losing_sync() -> None:
    junk = b"x" * (protocol.MAX_LINE_BYTES * 3)

    assert events(junk + b"\n" + protocol.encode_end()) == [End()]


def test_stream_stops_after_end_and_after_err() -> None:
    assert events(b"V END\nV P 0.5\n") == [End()]
    assert events(b"V ERR synthesis_failed boom\nV END\n") == [
        WorkerError("synthesis_failed", "boom")
    ]


def test_eof_without_end_just_stops() -> None:
    assert events(b"V P 0.5\nV P 0.7") == [Progress(0.5), Progress(0.7)]


@pytest.mark.parametrize(
    "header",
    [
        b"V A\n",
        b"V A 4 16000\n",
        b"V A four 16000 int16\n",
        b"V A 4 16000 mp3\n",
        b"V A 0 16000 int16\n",
        b"V A -4 16000 int16\n",
        b"V A 3 16000 int16\n",  # not a whole sample
        b"V A 6 16000 float32\n",
        b"V A 4 0 int16\n",
        b"V A 4 99999999 int16\n",
        b"V A 99999999999 16000 int16\n",
    ],
)
def test_malformed_audio_header_is_a_protocol_error(header: bytes) -> None:
    with pytest.raises(ProtocolError):
        events(header + b"\x00" * 8)


def test_truncated_pcm_is_a_protocol_error() -> None:
    with pytest.raises(ProtocolError, match="ended"):
        events(b"V A 10 16000 int16\n\x00\x00\x00")


def test_error_message_is_sanitized_and_paths_are_redacted() -> None:
    message = "cannot open /home/me/models/a.onnx\x07 or C:\\Users\\me\\b.onnx\tnow"

    clean = protocol.sanitize_message(message)

    assert clean == "cannot open <path> or <path> now"
    assert protocol.sanitize_message("x" * 500) == "x" * protocol.MAX_MESSAGE_CHARS
    assert protocol.encode_error("synthesis_failed", "a\nb\r\nc").count(b"\n") == 1


def test_error_record_carries_a_code_and_a_clean_message() -> None:
    record = protocol.encode_error("voice_not_found", "no voice at /srv/x")

    assert events(record) == [WorkerError("voice_not_found", "no voice at <path>")]
