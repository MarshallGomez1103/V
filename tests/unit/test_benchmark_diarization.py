"""Synthetic diarization benchmark: planning, scoring and process boundaries."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import wave
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/benchmark-diarization.py"
SPEC = importlib.util.spec_from_file_location("benchmark_diarization", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
bench = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bench
SPEC.loader.exec_module(bench)


def test_plan_does_not_import_runtime_or_spawn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("planning must not spawn or load models")

    monkeypatch.setattr(bench.subprocess, "Popen", forbidden)
    assert bench.main([]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "planned"
    assert plan["thresholds"] == [0.3, 0.4, 0.5, 0.6, 0.7]
    assert plan["device"] == "cpu"
    assert plan["threads"] == 2
    assert plan["results"] is None


@pytest.mark.parametrize("timeout", ["0", "61", "nan", "inf", "-1"])
def test_invalid_deadlines_are_rejected(timeout: str) -> None:
    assert bench.main(["--timeout-seconds", timeout]) == 2


def test_explicit_paths_are_required() -> None:
    assert bench.main(["--run"]) == 2


def test_paths_reject_existing_checkout_and_symlink_output(tmp_path: Path) -> None:
    model = tmp_path / "models"
    model.mkdir()
    for name in bench.MODEL_FILES:
        (model / name).write_bytes(b"synthetic")
    with pytest.raises(ValueError):
        bench.validate_paths(model, SCRIPT.parent / "forbidden")
    with pytest.raises(ValueError):
        bench.validate_paths(model, model)
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        bench.validate_paths(model, alias / "new-output")
    model_alias = tmp_path / "model-alias"
    model_alias.symlink_to(model, target_is_directory=True)
    with pytest.raises(ValueError):
        bench.validate_paths(model_alias, tmp_path / "new-output")


def test_scoring_uses_nominal_overlap_and_keeps_missing_or_tied_labels() -> None:
    reference = [
        bench.Span(0, 1000, "A"),
        bench.Span(1000, 2000, "B"),
        bench.Span(2000, 3000, "A"),
    ]
    turns = [
        bench.Span(0, 500, "x"),
        bench.Span(500, 1000, "y"),
        bench.Span(1000, 2000, "z"),
    ]
    result = bench.score(turns, reference)
    assert result["cluster_count"] == 3
    assert [item["dominant_cluster"] for item in result["utterances"]] == [
        None,
        "z",
        None,
    ]
    assert result["utterances"][0]["overlap_ms_by_cluster"] == {"x": 500, "y": 500}
    assert "accuracy" not in result and "der" not in result


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_failed_and_timed_out_processes_are_not_completed(tmp_path: Path) -> None:
    failure = tmp_path / "failure"
    failure.mkdir()
    result = bench.run_limited(
        [sys.executable, "-c", "raise SystemExit(7)"], failure, dict(os.environ), 1
    )
    assert result["status"] == "failed" and result["returncode"] == 7
    timeout = tmp_path / "timeout"
    timeout.mkdir()
    result = bench.run_limited(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        timeout,
        dict(os.environ),
        0.1,
    )
    assert result["status"] == "timed_out"
    assert result["reaped"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_successful_leader_does_not_leave_descendants(tmp_path: Path) -> None:
    script = (
        "import subprocess,sys,time\n"
        'child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(20)"])\n'
        "print(child.pid,flush=True)\n"
    )
    result = bench.run_limited(
        [sys.executable, "-c", script], tmp_path, dict(os.environ), 2
    )
    assert result["status"] == "completed"
    pid = int((tmp_path / "stdout.log").read_text())
    stat = Path(f"/proc/{pid}/stat")
    deadline = time.monotonic() + 1
    while stat.exists() and stat.read_text().split()[2] != "Z":
        assert time.monotonic() < deadline, "owned descendant survived SIGKILL"
        time.sleep(0.005)


def test_corpus_keeps_known_windows_and_synthetic_voices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    voices: list[str] = []

    def synthesize(
        command: list[str], directory: Path, env: dict[str, str], timeout: float
    ) -> dict[str, object]:
        if command[0] == "espeak-ng":
            voices.append(command[2])
        else:
            with wave.open(command[-1], "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16_000)
                audio.writeframes(bytes(32_000))
        assert timeout <= 60
        return {"status": "completed", "argv": command}

    monkeypatch.setattr(bench, "run_limited", synthesize)
    result = bench.make_corpus(tmp_path / "aba", ("es+f3", "es+m3", "es+f3"), {})
    assert voices == ["es+f3", "es+m3", "es+f3"]
    assert result["audio_seconds"] == 5
    assert [(item["start_ms"], item["end_ms"]) for item in result["utterances"]] == [
        (500, 1500),
        (2000, 3000),
        (3500, 4500),
    ]
    assert len(result["audio_sha256"]) == 64


def test_protected_namespace_is_rejected_before_filesystem_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(_path: Path) -> bool:
        pytest.fail("protected namespace must not be inspected")

    monkeypatch.setattr(Path, "is_symlink", forbidden)
    path = Path.home() / "safe" / ".." / ".local/share/voz" / "model"
    with pytest.raises(ValueError, match="personal application"):
        bench.external(path)
