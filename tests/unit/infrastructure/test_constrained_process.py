from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from voz.application.edge_lab import ExperimentDefinition, ResourceProfile
from voz.infrastructure import constrained_process as constrained

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX experiment tree")


def experiment(tmp_path: Path) -> ExperimentDefinition:
    return ExperimentDefinition(
        "stt",
        ResourceProfile(),
        "faster-whisper",
        "tiny",
        tmp_path / "dataset",
        tmp_path / "model",
        timeout_seconds=2,
    )


def script_factory(script: str, children: list[subprocess.Popen[bytes]]):
    def spawn(argv: list[str], **options: Any) -> subprocess.Popen[bytes]:
        assert options["stdin"] == subprocess.DEVNULL
        assert options["stdout"] == options["stderr"] == subprocess.DEVNULL
        assert options["shell"] is False and options["start_new_session"] is True
        assert "preexec_fn" not in options
        assert argv[1:3] == ["-m", constrained.WORKER_MODULE]
        child = cast(
            subprocess.Popen[bytes],
            subprocess.Popen(
                [sys.executable, "-c", script, *argv[3:]], text=False, **options
            ),
        )
        children.append(child)
        return child

    return spawn


@pytest.mark.parametrize("content", [None, b'{"measured": NaN}', b"[]", b"{"])
def test_fake_process_response_is_validated_and_always_cleaned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: bytes | None,
) -> None:
    cleaned: list[object] = []

    class FakeProcess:
        pid = 99_999_999

        def __init__(self, argv: list[str], **_options: Any) -> None:
            Path(argv[-2]).write_text(
                json.dumps({"effective": {"device": "cpu"}, "observations": {}})
            )
            Path(argv[-1]).write_bytes(
                content
                if content is not None
                else json.dumps(
                    {
                        "status": "completed",
                        "measured": {"fixture": 1},
                        "estimated": {},
                        "observations": {},
                    }
                ).encode()
            )

        def poll(self) -> int:
            return 0

    def spawn(argv: list[str], **options: Any) -> subprocess.Popen[bytes]:
        return cast(subprocess.Popen[bytes], FakeProcess(argv, **options))

    monkeypatch.setattr(constrained, "_stop_tree", cleaned.append)
    result = constrained.ConstrainedProcess(popen=spawn).run(experiment(tmp_path))
    if content is None:
        assert result.status == "completed" and result.measured == {"fixture": 1}
    else:
        assert result.status == "failed" and result.code == "lab_invalid_result"
    assert result.estimated == {} and len(cleaned) == 1


def test_real_child_limits_do_not_change_parent_limits_or_environment(
    tmp_path: Path,
) -> None:
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux affinity and address-space limits")
    import resource

    affinity = os.sched_getaffinity(0)
    memory = resource.getrlimit(resource.RLIMIT_AS)
    environment = dict(os.environ)
    children: list[subprocess.Popen[bytes]] = []
    script = """
import json, os, sys
from pathlib import Path
from voz.application.edge_lab import decode_definition
from voz.infrastructure.edge_lab_worker import apply_limits, _write
request, ready, result = map(Path, sys.argv[1:])
definition = decode_definition(request.read_bytes())
effective = apply_limits(definition.profile)
observations = {"offline": os.environ["HF_HUB_OFFLINE"],
                "cuda_visible": os.environ["CUDA_VISIBLE_DEVICES"]}
_write(ready, {"effective": effective, "observations": observations})
_write(result, {"status": "completed", "measured": {"fixture": 1},
                "estimated": {}, "observations": {}})
"""
    definition = replace(
        experiment(tmp_path), profile=ResourceProfile((min(affinity),), 2**30)
    )
    result = constrained.ConstrainedProcess(popen=script_factory(script, children)).run(
        definition
    )
    assert result.status == "completed", result
    effective = result.constraints["effective"]
    assert isinstance(effective, dict)
    assert effective["cpu_mask"] == [min(affinity)]
    assert effective["address_space_bytes"] == {"soft": 2**30, "hard": 2**30}
    assert effective["thread_environment"] == {
        name: "1"
        for name in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        )
    }
    assert result.observations["offline"] == "1"
    assert result.observations["cuda_visible"] == ""
    assert os.sched_getaffinity(0) == affinity
    assert resource.getrlimit(resource.RLIMIT_AS) == memory
    assert dict(os.environ) == environment
    assert children[0].returncode == 0


def test_missing_model_is_a_failure_even_after_real_worker_readiness(
    tmp_path: Path,
) -> None:
    result = constrained.ConstrainedProcess().run(
        replace(experiment(tmp_path), timeout_seconds=5)
    )
    assert result.status == "failed" and result.code == "lab_model_unavailable"
    assert result.measured == {} and result.estimated == {}
    assert result.observations["device"] == "cpu"
    assert str(tmp_path) not in json.dumps(result.observations)


@pytest.mark.parametrize(
    "profile,code",
    [
        (ResourceProfile(systemd=True), "lab_limit_unsupported"),
        (ResourceProfile(device="cuda"), "lab_device_unavailable"),
    ],
)
def test_unsupported_controls_never_spawn(
    tmp_path: Path, profile: ResourceProfile, code: str
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        raise AssertionError("must not spawn")

    result = constrained.ConstrainedProcess(popen=forbidden).run(
        replace(experiment(tmp_path), profile=profile)
    )
    assert result.code == code and result.measured == {}


@pytest.mark.parametrize("cancel", [False, True])
def test_deadline_and_cancellation_stop_child_and_stubborn_descendant(
    tmp_path: Path, cancel: bool
) -> None:
    pid_file = tmp_path / "descendant.pid"
    children: list[subprocess.Popen[bytes]] = []
    script = """
import json, subprocess, sys, time
from pathlib import Path
request, ready, result = map(Path, sys.argv[1:])
pid_file = json.loads(request.read_text())["input"]["path"]
code = '''import os,signal,sys,time
from pathlib import Path
signal.signal(signal.SIGTERM,signal.SIG_IGN)
Path(sys.argv[1]).write_text(str(os.getpid()))
time.sleep(60)
'''
descendant = subprocess.Popen([sys.executable, "-c", code, pid_file])
ready.write_text(json.dumps({"effective": {}, "observations": {}}))
time.sleep(60)
"""

    class CancelAfterSpawn:
        def is_cancelled(self) -> bool:
            return cancel and pid_file.exists()

    definition = replace(experiment(tmp_path), input_path=pid_file, timeout_seconds=0.5)
    result = constrained.ConstrainedProcess(popen=script_factory(script, children)).run(
        definition, CancelAfterSpawn()
    )
    assert result.code == ("lab_cancelled" if cancel else "lab_timeout")
    assert children[0].returncode is not None
    pid = int(pid_file.read_text())
    status = Path(f"/proc/{pid}/stat")
    deadline = time.monotonic() + 1.0
    while (
        sys.platform.startswith("linux")
        and status.exists()
        and time.monotonic() < deadline
    ):
        try:
            if status.read_text().split()[2] == "Z":
                break
        except FileNotFoundError:
            break
        time.sleep(0.01)
    if sys.platform.startswith("linux") and status.exists():
        # An orphan may await its system reaper; it must no longer execute.
        assert status.read_text().split()[2] == "Z"
    else:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_setup_hang_has_separate_readiness_deadline(tmp_path: Path) -> None:
    children: list[subprocess.Popen[bytes]] = []
    runner = constrained.ConstrainedProcess(
        popen=script_factory("import time; time.sleep(60)", children),
        ready_timeout_seconds=0.1,
    )
    result = runner.run(experiment(tmp_path))
    assert result.code == "lab_timeout" and result.observations == {}
    assert children[0].returncode is not None


def test_private_run_directory_is_removed(tmp_path: Path) -> None:
    result = constrained.ConstrainedProcess().run(experiment(tmp_path))
    assert result.status == "failed"
    from voz.infrastructure.paths import resolve_voz_paths

    assert list((resolve_voz_paths().cache / "edge-lab").iterdir()) == []


def test_direct_port_normalizes_paths_before_private_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[dict[str, Any]] = []

    def capture(argv: list[str], **_options: object) -> subprocess.Popen[bytes]:
        requests.append(json.loads(Path(argv[-3]).read_text()))
        raise OSError("fixture spawn failed")

    monkeypatch.chdir(tmp_path)
    definition = replace(
        experiment(tmp_path),
        input_path=Path("~/dataset"),
        model_directory=Path("model"),
    )
    constrained.ConstrainedProcess(popen=capture).run(definition)
    assert requests[0]["input"]["path"] == str(Path.home() / "dataset")
    assert requests[0]["model"]["directory"] == str(tmp_path / "model")
