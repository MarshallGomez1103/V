from __future__ import annotations

import subprocess
import sys

import pytest

from voz.infrastructure.child_env import child_environment

SOURCE = {
    "OPENAI_API_KEY": "sk-secret",
    "ELEVENLABS_API_KEY": "xi-secret",
    "MY_TOKEN": "t",
    "PATH": "/usr/bin",
    "SYSTEMROOT": r"C:\Windows",
    "CUDA_VISIBLE_DEVICES": "0",
    "HF_HUB_OFFLINE": "1",
    "UNRELATED": "x",
}


def test_only_technical_variables_survive() -> None:
    assert child_environment(source=SOURCE) == {
        "PATH": "/usr/bin",
        "SYSTEMROOT": r"C:\Windows",
        "CUDA_VISIBLE_DEVICES": "0",
        "HF_HUB_OFFLINE": "1",
    }


def test_gpu_selection_and_shell_variables_pass() -> None:
    source = {
        name: "1"
        for name in (
            "LANGUAGE",
            "DRI_PRIME",
            "PSModulePath",
            "MESA_LOADER_DRIVER_OVERRIDE",
            "RADV_PERFTEST",
            "OCL_ICD_VENDORS",
            "__NV_PRIME_RENDER_OFFLOAD",
            "__GLX_VENDOR_LIBRARY_NAME",
            "__VK_LAYER_NV_optimus",
            "ZES_ENABLE_SYSMAN",
            "SYCL_DEVICE_FILTER",
            "VK_ICD_FILENAMES",
            "GGML_VK_VISIBLE_DEVICES",
        )
    }
    assert child_environment(source=source) == source


def test_matching_is_case_insensitive_and_keeps_original_spelling() -> None:
    source = {"Path": "/bin", "SystemRoot": "C:", "lc_all": "C", "openai_api_key": "k"}
    assert child_environment(source=source) == {
        "Path": "/bin",
        "SystemRoot": "C:",
        "lc_all": "C",
    }


def test_secret_words_win_over_allowed_prefixes() -> None:
    source = {
        "CUDA_API_KEY": "a",
        "XDG_SECRET_DIR": "b",
        "OMP_PASSWORD": "c",
        "HF_TOKEN": "d",
        "NVIDIA_CREDENTIAL": "e",
        "XDG_DATA_HOME": "/data",
    }
    assert child_environment(source=source) == {"XDG_DATA_HOME": "/data"}


def test_extra_overrides_source_even_with_different_case() -> None:
    result = child_environment(
        {"HF_HUB_OFFLINE": "1", "CUDA_VISIBLE_DEVICES": ""},
        source={"cuda_visible_devices": "0", "PATH": "/bin"},
    )
    assert result == {
        "PATH": "/bin",
        "HF_HUB_OFFLINE": "1",
        "CUDA_VISIBLE_DEVICES": "",
    }


def test_default_source_is_the_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("PATH", "/somewhere")
    result = child_environment()
    assert result["PATH"] == "/somewhere"
    assert "OPENAI_API_KEY" not in result


def test_a_real_child_starts_without_the_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    completed = subprocess.run(
        [sys.executable, "-c", "import os; print(sorted(os.environ))"],
        env=child_environment(),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert "OPENAI_API_KEY" not in completed.stdout
