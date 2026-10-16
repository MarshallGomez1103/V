"""Pure, measured-only Markdown projection of Edge Lab version-one reports."""

from __future__ import annotations

import html
import json
import math
import unicodedata
from collections.abc import Sequence
from typing import cast

from voz.application.edge_lab import ERROR_MESSAGES, MAX_RESULT_BYTES

UNKNOWN = "—"
HEADERS = (
    "Status",
    "Model (engine)",
    "Device (effective)",
    "CPU mask (effective)",
    "AS soft / hard (bytes, effective)",
    "STT RTF",
    "STT WER",
    "TTS first chunk (s)",
    "TTS throughput (audio s / wall s)",
    "STT peak RSS (MiB; scope)",
    "TTS worker peak RSS (MiB)",
    "TTS largest child peak RSS (MiB)",
)


class ComparisonError(ValueError):
    """A fixed message safe for transport, without report data or file paths."""

    def __init__(self) -> None:
        super().__init__("The experiment report is invalid or unavailable.")


def _mapping(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ComparisonError
    return cast(dict[str, object], value)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ComparisonError
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise ComparisonError


def _finite_tree(value: object) -> None:
    if type(value) in (int, float):
        if not math.isfinite(cast(int | float, value)):
            raise ComparisonError
    elif isinstance(value, dict):
        for item in cast(dict[str, object], value).values():
            _finite_tree(item)
    elif isinstance(value, list):
        for item in cast(list[object], value):
            _finite_tree(item)


def _decode(raw: bytes) -> dict[str, object]:
    if len(raw) > MAX_RESULT_BYTES:
        raise ComparisonError
    try:
        value: object = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
        _finite_tree(value)
        data = _mapping(value)
        required = {
            "schema_version",
            "status",
            "code",
            "measured",
            "estimated",
            "observations",
            "constraints",
        }
        if not required <= data.keys() <= required | {"message"}:
            raise ComparisonError
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ComparisonError
        status, code = data["status"], data["code"]
        if status == "completed":
            if code is not None:
                raise ComparisonError
        elif status == "failed":
            if not isinstance(code, str) or code not in ERROR_MESSAGES:
                raise ComparisonError
            if code in ("lab_cancelled", "lab_timeout"):
                raise ComparisonError
        elif (status, code) not in (
            ("cancelled", "lab_cancelled"),
            ("timed_out", "lab_timeout"),
        ):
            raise ComparisonError
        for key in ("measured", "estimated", "observations", "constraints"):
            if not isinstance(data[key], dict):
                raise ComparisonError
        if status != "completed" and data["measured"]:
            raise ComparisonError
        return data
    except (ValueError, TypeError, RecursionError, OverflowError) as error:
        raise ComparisonError from error


def _metric(value: object) -> str:
    if value is None:
        return UNKNOWN
    if type(value) not in (int, float) or cast(int | float, value) < 0:
        raise ComparisonError
    return format(cast(int | float, value), ".6g")


def _label(value: object) -> str:
    if value is None:
        return UNKNOWN
    if not isinstance(value, str) or len(value) > 4096:
        raise ComparisonError
    # Labels containing path separators are withheld, including relative paths.
    if "/" in value or "\\" in value or value.startswith("~"):
        return UNKNOWN
    text = " ".join(
        "".join(
            " " if unicodedata.category(char).startswith("C") else char
            for char in value
        ).split()
    )
    if not text:
        return UNKNOWN
    text = html.escape(text, quote=False)
    for char in ("|", "`", "*", "_", "[", "]"):
        text = text.replace(char, "\\" + char)
    return text


def _mask(value: object) -> str:
    if value is None:
        return UNKNOWN
    if not isinstance(value, list):
        raise ComparisonError
    ids = cast(list[object], value)
    if (
        not ids
        or len(ids) > 4096
        or any(type(cpu) is not int or cpu < 0 for cpu in ids)
    ):
        raise ComparisonError
    cpus = cast(list[int], ids)
    if len(set(cpus)) != len(cpus):
        raise ComparisonError
    return ", ".join(map(str, cpus))


def _address_space(value: object) -> str:
    if value is None:
        return UNKNOWN
    limits = _mapping(value)
    cells: list[str] = []
    for name in ("soft", "hard"):
        limit = limits.get(name)
        if limit is None:
            cells.append(UNKNOWN)
        elif type(limit) is int and 0 < limit < 2**63:
            cells.append(str(limit))
        else:
            raise ComparisonError
    return " / ".join(cells)


def _row(raw: bytes) -> tuple[str, ...]:
    data = _decode(raw)
    measured = _mapping(data["measured"])
    observations = _mapping(data["observations"])
    effective = _mapping(_mapping(data["constraints"]).get("effective"))
    model = _mapping(observations.get("model"))
    model_id, engine = _label(model.get("model_id")), _label(model.get("engine"))
    model_cell = model_id
    if model_id != UNKNOWN and engine != UNKNOWN:
        model_cell += f" ({engine})"
    device = effective.get("device")
    if device is not None and device not in ("cpu", "cuda"):
        raise ComparisonError
    totals = _mapping(measured.get("totals"))
    memory = _mapping(measured.get("memory"))
    ram = _metric(memory.get("ram_peak_mib"))
    if ram != UNKNOWN:
        method = _mapping(measured.get("methods")).get("ram")
        scope = (
            "worker"
            if method == "worker peak RSS"
            else "largest completed child"
            if method == "largest completed child peak RSS"
            else "unknown scope"
        )
        ram += f" ({scope})"
    return (
        cast(str, data["status"]),
        model_cell,
        cast(str, device or UNKNOWN),
        _mask(effective.get("cpu_mask")),
        _address_space(effective.get("address_space_bytes")),
        _metric(totals.get("rtf")),
        _metric(totals.get("wer")),
        _metric(measured.get("first_audio_seconds")),
        _metric(measured.get("throughput_audio_seconds_per_second")),
        ram,
        _metric(memory.get("worker_peak_rss_mib")),
        _metric(memory.get("largest_child_peak_rss_mib")),
    )


def render_comparison(reports: Sequence[bytes]) -> str:
    """Validate every envelope before producing a table in input order."""
    if not reports:
        raise ComparisonError
    rows = [_row(raw) for raw in reports]
    return (
        "\n".join(
            "| " + " | ".join(row) + " |"
            for row in (HEADERS, ("---",) * len(HEADERS), *rows)
        )
        + "\n"
    )
