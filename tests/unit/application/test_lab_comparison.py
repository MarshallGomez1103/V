from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from voz.application.edge_lab import MAX_RESULT_BYTES, ExperimentResult
from voz.application.lab_comparison import ComparisonError, render_comparison


def encoded(
    *,
    status: str = "completed",
    code: str | None = None,
    measured: dict[str, object] | None = None,
    observations: dict[str, object] | None = None,
    constraints: dict[str, object] | None = None,
) -> bytes:
    return json.dumps(
        asdict(
            ExperimentResult(
                status,
                code,
                measured=measured or {},
                observations=observations or {},
                constraints=constraints or {},
            )
        )
    ).encode()


def test_compare_current_stt_and_tts_envelopes_without_summing_rss() -> None:
    stt = encoded(
        measured={
            "totals": {"rtf": 0.25, "wer": 0.0},
            "memory": {"ram_peak_mib": 24.0},
            "methods": {"ram": "worker peak RSS"},
        },
        observations={"model": {"engine": "faster-whisper", "model_id": "tiny"}},
        constraints={
            "effective": {
                "device": "cpu",
                "cpu_mask": [1, 3],
                "address_space_bytes": {"soft": 1073741824, "hard": 1073741824},
            }
        },
    )
    tts = encoded(
        measured={
            "first_audio_seconds": 0.5,
            "throughput_audio_seconds_per_second": 2.0,
            "memory": {
                "worker_peak_rss_mib": 12.0,
                "largest_child_peak_rss_mib": 30.0,
            },
        },
        observations={"model": {"engine": "sherpa-onnx-tts", "model_id": "voice"}},
    )
    table = render_comparison([stt, tts])
    rows = table.splitlines()
    assert len(rows) == 4
    assert "tiny (faster-whisper)" in rows[2]
    assert "| cpu | 1, 3 | 1073741824 / 1073741824 | 0.25 | 0 |" in rows[2]
    assert "24 (worker)" in rows[2]
    assert "voice (sherpa-onnx-tts)" in rows[3]
    assert "| 0.5 | 2 | — | 12 | 30 |" in rows[3]
    assert "42" not in table
    assert "first chunk" in rows[0] and "largest child" in rows[0]


@pytest.mark.parametrize(
    "status,code",
    [
        ("failed", "lab_worker_failed"),
        ("cancelled", "lab_cancelled"),
        ("timed_out", "lab_timeout"),
    ],
)
def test_unsuccessful_reports_stay_unsuccessful_and_requested_is_not_effective(
    status: str, code: str
) -> None:
    table = render_comparison(
        [
            encoded(
                status=status, code=code, constraints={"requested": {"device": "cpu"}}
            )
        ]
    )
    assert table.splitlines()[2] == f"| {status} | " + "— | " * 10 + "— |"
    assert "completed" not in table


@pytest.mark.parametrize(
    "status,code",
    [
        ("failed", "lab_worker_failed"),
        ("cancelled", "lab_cancelled"),
        ("timed_out", "lab_timeout"),
    ],
)
@pytest.mark.parametrize("measured", [{"totals": {"rtf": 0}}, {"memory": None}])
def test_unsuccessful_reports_cannot_contain_measurements(
    status: str, code: str, measured: dict[str, object]
) -> None:
    with pytest.raises(ComparisonError):
        render_comparison([encoded(status=status, code=code, measured=measured)])


def test_missing_null_and_zero_are_distinct_and_estimates_are_not_measurements() -> (
    None
):
    payload = json.loads(
        encoded(
            measured={
                "totals": {"rtf": 0, "wer": None},
                "first_audio_seconds": 0,
                "memory": {"worker_peak_rss_mib": None},
            }
        )
    )
    payload["estimated"] = {"throughput_audio_seconds_per_second": 9876}
    row = render_comparison([json.dumps(payload).encode()]).splitlines()[2]
    assert "| 0 | — | 0 | — |" in row
    assert "9876" not in row
    assert row.endswith("| — | — | — |")


def test_rss_scope_is_preserved_and_unknown_scope_is_explicit() -> None:
    for method, scope in [
        ("largest completed child peak RSS", "largest completed child"),
        ("private unknown method", "unknown scope"),
    ]:
        table = render_comparison(
            [
                encoded(
                    measured={"memory": {"ram_peak_mib": 4}, "methods": {"ram": method}}
                )
            ]
        )
        assert f"4 ({scope})" in table
        assert "private unknown method" not in table


def test_model_cells_escape_markdown_and_do_not_echo_other_report_content() -> None:
    payload = json.loads(
        encoded(
            observations={
                "model": {
                    "model_id": "tiny|demo\nnext",
                    "engine": "engine<demo>",
                    "source": "/private/model",
                },
                "input_text": "secret input",
                "command": "secret command",
            }
        )
    )
    payload["message"] = "/private/error secret message"
    table = render_comparison([json.dumps(payload).encode()])
    assert len(table.splitlines()) == 3
    assert "tiny\\|demo next (engine&lt;demo&gt;)" in table
    for secret in ("/private", "secret", "input_text", "command"):
        assert secret not in table


@pytest.mark.parametrize(
    "label", ["/private/model", "../private/model", "C:\\private\\model"]
)
def test_path_like_model_labels_are_redacted(label: str) -> None:
    table = render_comparison([encoded(observations={"model": {"model_id": label}})])
    assert label not in table
    assert table.splitlines()[2].startswith("| completed | — |")


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[]",
        b'{"schema_version":1,"schema_version":1}',
        b"\xff",
        b"[" * 2000,
    ],
)
def test_invalid_json_is_a_fixed_safe_error(raw: bytes) -> None:
    with pytest.raises(
        ComparisonError, match=r"^The experiment report is invalid or unavailable\.$"
    ):
        render_comparison([raw])


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("status", "success"),
        ("status", "failed"),
        ("code", "lab_worker_failed"),
        ("measured", []),
        ("observations", None),
        ("constraints", "invalid"),
    ],
)
def test_invalid_envelopes_are_not_presented_as_success(
    field: str, value: object
) -> None:
    payload = json.loads(encoded())
    payload[field] = value
    with pytest.raises(ComparisonError):
        render_comparison([json.dumps(payload).encode()])


@pytest.mark.parametrize("value", [True, "0.2", -1, float("nan"), float("inf"), 1e309])
def test_metrics_must_be_finite_nonnegative_numbers(value: object) -> None:
    with pytest.raises(ComparisonError):
        render_comparison([encoded(measured={"totals": {"rtf": value}})])


@pytest.mark.parametrize("value", [float("nan"), float("-inf"), 10**400])
def test_nonfinite_values_are_rejected_even_in_unrendered_sections(
    value: object,
) -> None:
    with pytest.raises(ComparisonError):
        render_comparison([encoded(observations={"unrendered": {"value": value}})])


@pytest.mark.parametrize(
    "effective",
    [
        {"cpu_mask": [True]},
        {"cpu_mask": [1, 1]},
        {"cpu_mask": []},
        {"address_space_bytes": 1024},
        {"address_space_bytes": {"soft": -1}},
        {"device": "/private/device"},
    ],
)
def test_invalid_effective_controls_are_rejected(effective: dict[str, object]) -> None:
    with pytest.raises(ComparisonError):
        render_comparison([encoded(constraints={"effective": effective})])


def test_empty_comparison_and_oversize_are_rejected() -> None:
    for reports in ([], [b" " * (MAX_RESULT_BYTES + 1)]):
        with pytest.raises(ComparisonError):
            render_comparison(reports)
