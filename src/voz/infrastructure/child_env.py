"""Minimal environment for child processes: technical variables only, never secrets."""

from __future__ import annotations

import os
from collections.abc import Mapping

# Names are compared upper-cased: Windows environment keys ignore case.
_EXACT = frozenset(
    {
        "PATH",
        "PATHEXT",
        "HOME",
        "USER",
        "USERNAME",
        "LOGNAME",
        "SHELL",
        "TERM",
        "TZ",
        "LANG",
        "LANGUAGE",
        "DRI_PRIME",
        "PSMODULEPATH",
        "LD_LIBRARY_PATH",
        "VIRTUAL_ENV",
        "TMPDIR",
        "TEMP",
        "TMP",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "ALLUSERSPROFILE",
        "PUBLIC",
        "OS",
        "COMPUTERNAME",
        "NUMBER_OF_PROCESSORS",
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
        "HF_DATASETS_OFFLINE",
    }
)
_PREFIXES = (
    "LC_",
    "XDG_",
    "DYLD_",
    "PYTHON",
    "PROGRAM",
    "COMMONPROGRAM",
    "PROCESSOR_",
    "CUDA_",
    "NVIDIA_",
    "HIP_",
    "HSA_",
    "ROCR_",
    "ROCM_",
    "VK_",
    "GGML_",
    "ORT_",
    "MTL_",
    "MESA_",
    "RADV_",
    "OCL_",
    "__NV_",
    "__GLX_",
    "__VK_",
    "ZES_",
    "SYCL_",
    "OMP_",
    "GOMP_",
    "KMP_",
    "MKL_",
    "OPENBLAS_",
    "NUMEXPR_",
)
# A secret-looking word wins over any allowed name or prefix.
_SECRET_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "AUTH")


def _allowed(name: str) -> bool:
    upper = name.upper()
    if any(word in upper for word in _SECRET_WORDS):
        return False
    return upper in _EXACT or upper.startswith(_PREFIXES)


def child_environment(
    extra: Mapping[str, str] | None = None,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Allowlisted copy of ``source`` (default: this process) plus trusted ``extra``."""
    variables = os.environ if source is None else source
    environment = {name: value for name, value in variables.items() if _allowed(name)}
    for name, value in (extra or {}).items():
        for existing in [key for key in environment if key.upper() == name.upper()]:
            del environment[existing]
        environment[name] = value
    return environment
