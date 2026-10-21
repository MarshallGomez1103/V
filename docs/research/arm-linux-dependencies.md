# Linux aarch64 (ARM) availability of V's dependencies

Slice V9-01. Research only: no code was changed and nothing was run on ARM
hardware. Query date for every PyPI/GitHub fact below: **2026-10-11**.

## Scope and honesty rule

This document answers one narrow question: **do the pieces exist for Linux
aarch64 + CPython 3.12, or are they missing?** It does **not** say that V works on
ARM. Nobody has installed or run V on an ARM machine; that needs hardware and is a
separate slice (V9-02). The [edge feasibility review](edge-feasibility.md)
discusses possible single-board-computer speech workloads; actual compatibility
and performance remain unmeasured on a board.

Legend used throughout:

- **Verified (source)**: read from the cited primary source on the query date.
- **Not verified**: inferred, remembered, or not checked. Never treat it as a fact.

"Wheel for aarch64" means a binary wheel whose filename tags include `aarch64`
with a `manylinux*` platform tag, for `cp312` (or `abi3` / `py3-none`, which also
install on 3.12). Pure-Python wheels (`py3-none-any`) install on any architecture.

## How the data was obtained

For each package the JSON API `https://pypi.org/pypi/<package>/json` was read
(the same data as the human page `https://pypi.org/project/<package>/#files`) and
the file list was filtered by filename. Two views were taken:

1. **Latest release** at the query date (column "Latest").
2. **The version V has locked** in [`uv.lock`](../../uv.lock) (read from the
   wheel URLs recorded in the lock file). This is what `uv sync` would pick, so it
   matters more than "latest". The lock file already lists the aarch64 wheels, so
   resolution itself does not need a build on ARM for the packages below.

Wheel sizes are those shown by the PyPI JSON for the latest release.

## 1. Base dependencies (`[project].dependencies`)

Declared in [`pyproject.toml`](../../pyproject.toml).

| Dependency | Wheel kind (latest) | Linux aarch64 wheel for CPython 3.12? | Locked in V | Source |
|---|---|---|---|---|
| fastapi | `py3-none-any` (pure Python) | Not needed: pure Python installs everywhere. Verified. | 0.141.1 (`any`) | [PyPI json](https://pypi.org/pypi/fastapi/json) |
| uvicorn | `py3-none-any` | Not needed (pure). Verified. | 0.52.4 (`any`) | [PyPI json](https://pypi.org/pypi/uvicorn/json) |
| alembic | `py3-none-any` | Not needed (pure). Verified. | 1.19.1 (`any`) | [PyPI json](https://pypi.org/pypi/alembic/json) |
| typer | `py3-none-any` | Not needed (pure). Verified. | 0.27.2 (`any`) | [PyPI json](https://pypi.org/pypi/typer/json) |
| sqlalchemy | Compiled (optional C extensions) plus a `py3-none-any` fallback | **Yes.** `cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64` (also musllinux). Latest 2.1.4. Verified. | 2.0.52 has the same manylinux aarch64 cp312 wheel | [PyPI json](https://pypi.org/pypi/sqlalchemy/json) |

Result: the five direct base dependencies are either pure Python (fastapi,
uvicorn, alembic, typer) or ship an aarch64 wheel (sqlalchemy), and even
sqlalchemy has a pure-Python wheel, so it could never block an install.

### Compiled transitive dependencies of the base set

The "normally pure Python" assumption is true for the five direct packages but
not for everything they pull in. Verified in `uv.lock` (cp312, aarch64 manylinux):

| Transitive package | Pulled by | Locked version | aarch64 manylinux cp312 wheel |
|---|---|---|---|
| pydantic-core | fastapi (via pydantic) | 2.46.5 | Yes (`manylinux_2_17_aarch64`) |
| markupsafe | alembic (via Mako) | 3.0.3 | Yes (`manylinux2014_aarch64`) |
| greenlet | present in the lock (not a hard dependency of sqlalchemy 2.x core) | 3.5.5 | Yes (`manylinux_2_24_aarch64`) |

Packages the lock marks pure Python (`any`): mako 1.4.1. Other transitive pure
packages (starlette, click, h11, rich, shellingham, ...) were **not
individually checked**: not verified, but they are standard pure-Python
libraries.

## 2. Extra `asr-local`

| Dependency | Wheel kind (latest) | Linux aarch64 wheel for CPython 3.12? | Locked in V | Source |
|---|---|---|---|---|
| faster-whisper 1.2.1 | `py3-none-any` | Not needed (pure). Verified. Its dependencies (below) are what matter. | 1.2.1 | [PyPI json](https://pypi.org/pypi/faster-whisper/json) |
| ctranslate2 | Compiled | **Yes.** `ctranslate2-4.8.2-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl` (16.9 MB, uploaded 2026-08-31). Verified. | 4.8.2 (same wheel) | [PyPI json](https://pypi.org/pypi/ctranslate2/json) |
| nvidia-cublas-cu12 | Compiled, `py3-none` | Wheel exists: `nvidia_cublas_cu12-12.9.2.10-py3-none-manylinux_2_27_aarch64.whl` (575 MB). Verified that the file exists. **Whether it is useful on a SBC: see the finding below.** | 12.9.2.10 | [PyPI json](https://pypi.org/pypi/nvidia-cublas-cu12/json) |
| nvidia-cudnn-cu12 | Compiled, `py3-none` | Wheel exists: `nvidia_cudnn_cu12-9.27.0.42-py3-none-manylinux_2_27_aarch64.whl` (772.7 MB). Verified that the file exists. Same caveat. | 9.27.0.42 | [PyPI json](https://pypi.org/pypi/nvidia-cudnn-cu12/json) |

Dependencies of faster-whisper 1.2.1 (from the PyPI metadata): `ctranslate2`,
`huggingface-hub`, `tokenizers`, `onnxruntime`, `av`, `tqdm`. The compiled ones
were checked in `uv.lock` for cp312 / abi3 aarch64 manylinux:

| Package | Locked version | aarch64 manylinux wheel | Note |
|---|---|---|---|
| onnxruntime | 1.29.0 | Yes (`cp312-cp312-manylinux_2_28_aarch64`). Latest 1.31.0 also has it (21.4 MB). | Verified. Comes from faster-whisper, **not** from sherpa-onnx (see section 3). |
| av (PyAV) | 18.1.0 | Yes (`cp311-abi3-manylinux_2_28_aarch64`, installs on 3.12) | Verified. |
| tokenizers | 0.23.2 | Yes (`cp310-abi3-manylinux_2_17_aarch64`) | Verified. |
| hf-xet | 1.6.0 | Yes (`cp38-abi3-manylinux_2_28_aarch64`) | Verified (lock file). |
| pyyaml | 6.0.3 | Yes (`cp312-cp312-manylinux2014_aarch64`) | Verified (ctranslate2 dependency). |
| numpy | 2.5.2 | Yes (`cp312-cp312-manylinux_2_27_aarch64`) | Verified (ctranslate2 dependency). |
| protobuf | 7.36.1 | Yes (`cp310-abi3-manylinux2014_aarch64`) | Verified (onnxruntime dependency). |

CPU backend: the ctranslate2 package description on PyPI states that the project
supports x86-64 and AArch64/ARM64 processors with backends including OpenBLAS
and Ruy ([PyPI project page](https://pypi.org/project/ctranslate2/)). Verified as
a statement of the project. **Not verified**: which backend the published aarch64
wheel actually bundles, its int8 speed on a Raspberry Pi class CPU, and whether the
aarch64 wheel contains any CUDA code. That has to be measured.

### Finding: the CUDA marker does not distinguish architectures

[`pyproject.toml`](../../pyproject.toml) declares:

```toml
"nvidia-cublas-cu12>=12.4,<13; sys_platform == 'linux' or sys_platform == 'win32'",
"nvidia-cudnn-cu12>=9.1,<10; sys_platform == 'linux' or sys_platform == 'win32'",
```

The marker only looks at the operating system. On Linux aarch64 it still selects
both packages. Consequences, with their evidence level:

- **Verified**: aarch64 wheels of both packages exist on PyPI, so resolution
  succeeds and the lock file is satisfied. Together they are about 1.35 GB
  (575 MB + 772.7 MB) for the latest release, plus `nvidia-cuda-nvrtc-cu12`
  (a dependency of cublas, 12.9.86 in the lock, aarch64 wheel present). They are
  downloaded and unpacked on every `asr-local` install, regardless of whether the
  machine can use them.
- **Verified (code)**: V only uses them when the chosen device is `cuda`
  ([`faster_whisper.py`](../../src/voz/infrastructure/asr/faster_whisper.py),
  `_preload_cuda_libraries` and the CPU fallback `_cpu_fallback_notice`). When the
  libraries fail to load it falls back to CPU int8. So on a SBC without a CUDA
  GPU they are dead weight, not a crash, **as far as the code reads**.
- **Not verified**: that the preload step is harmless on an ARM machine
  (it dlopens every `lib*.so.*` under the `nvidia/*/lib` folders; a failure is
  retried and eventually skipped by design, but this was never run on aarch64).
  Also not verified: whether those aarch64 wheels target only server-class ARM
  with NVIDIA GPUs (SBSA) and not Jetson boards. The PyPI filenames do not say.
  Treat the aarch64 CUDA wheels as unusable on a Raspberry Pi / Orange Pi / most
  RK3588 boards until shown otherwise.
- **Install-size risk**: a 1.35 GB download on an SD-card or eMMC device is a
  practical blocker even if it is harmless.

This is a finding for a future slice (see the change list at the end), not
something fixed here.

## 3. Extra `diarization`

| Dependency | Wheel kind (latest) | Linux aarch64 wheel for CPython 3.12? | Locked in V | Source |
|---|---|---|---|---|
| numpy | Compiled | **Yes.** `numpy-2.5.4-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl` (15.7 MB, uploaded 2026-10-10); also musllinux. Verified. | 2.5.2 (same tags) | [PyPI json](https://pypi.org/pypi/numpy/json) |
| sherpa-onnx | Compiled | **Yes.** `sherpa_onnx-1.13.8-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.whl` (4.2 MB, uploaded 2026-09-10). Verified. | 1.13.8 (same wheel) | [PyPI json](https://pypi.org/pypi/sherpa-onnx/json) |
| sherpa-onnx-core | Compiled, `py3-none` | **Yes.** `sherpa_onnx_core-1.13.8-py3-none-manylinux2014_aarch64.whl` (13.4 MB). Verified. | 1.13.8 | [PyPI json](https://pypi.org/pypi/sherpa-onnx-core/json) |

Is `onnxruntime` a dependency of sherpa-onnx? **No (verified).** The PyPI
metadata of `sherpa-onnx` 1.13.8 lists a single hard dependency,
`sherpa-onnx-core==1.13.8`, and `sherpa-onnx-core` lists none. sherpa-onnx ships
its own bundled ONNX Runtime inside the `-core` wheel (the 13.4 MB aarch64 file).
The separate `onnxruntime` Python package is installed only through
`asr-local` (faster-whisper). So a `diarization`-only install on aarch64 does not
need the `onnxruntime` wheel; an `asr-local` install does.

Note: the pin `sherpa-onnx-core==1.13.8` in `pyproject.toml` is justified by the
cp314 wheel, per the comment there. It does not affect aarch64 on 3.12: the cp312
aarch64 wheel and the core wheel for the same version both exist.

**Not verified**: that the bundled ONNX Runtime inside the sherpa wheels uses the
ARM CPU efficiently (NEON paths), and the runtime speed of diarization on ARM.

## 4. FFmpeg

How V obtains FFmpeg
([`ffmpeg_tools.py`](../../src/voz/infrastructure/audio/ffmpeg_tools.py)):

1. A system `ffmpeg` and `ffprobe` on `PATH` is always preferred.
2. Otherwise it downloads one pinned bundle from the `zackees/ffmpeg_bins`
   repository (commit `df95abcb...`, folder `v8.0`), checks a SHA-256 and unpacks
   only `ffmpeg` and `ffprobe`.
3. The bundle key comes from `platform_key()`: `linux` becomes `linux_arm64` when
   `platform.machine()` is `arm64` or `aarch64`. A `linux_arm64` entry exists in
   the digest table (about 132 MB). A unit test covers the mapping
   (`("linux", "aarch64", "linux_arm64")` in
   [`test_ffmpeg_tools.py`](../../tests/unit/infrastructure/audio/test_ffmpeg_tools.py)).
   The user-facing description is in
   [`docs/install/windows-macos.md`](../install/windows-macos.md).

So **yes, the code contemplates aarch64** on Linux. Additional checks done for this
slice (verified on 2026-10-11):

- The pinned `linux_arm64.zip` can be downloaded from
  `https://github.com/zackees/ffmpeg_bins/raw/df95abcb0ce6efff710dda5ef28a2f6f1dc21493/v8.0/linux_arm64.zip`
  (131.8 MB) and its SHA-256 equals the digest in `_BUNDLES`
  (`e03efe47...97d6f`).
- It contains `linux_arm64/ffmpeg` and `linux_arm64/ffprobe`, as the extractor
  expects. `file` / `readelf` report both as 64-bit ELF **ARM aarch64**.
- They are **not fully static**: the executables are dynamically linked against
  glibc (`ld-linux-aarch64.so.1`, `libc.so.6`, `libm`, `libdl`, `librt`,
  `libpthread`, `libgcc_s`). The codecs are built in, but the machine needs a
  glibc-based userland. Alpine/musl and other non-glibc systems would not run
  them. Not executed here (no ARM hardware), so "runs on a real Pi" is **not
  verified**.
- A distribution FFmpeg (`apt install ffmpeg`) is the lower-risk path on a
  Debian-family SBC and is always preferred by V anyway.

**Not verified**: the minimum glibc version these binaries require, the
license/codec set of the zackees build for redistribution, and whether the build
runs on a Pi 5 class CPU without illegal instructions.

## 5. whisper.cpp (alternative engine)

V already has an adapter and docs for it
([`docs/whisper-cpp.md`](../whisper-cpp.md)): V launches an external `whisper-cli`
binary found by `VOZ_WHISPER_CPP_BIN` or on `PATH`.

Verified from the upstream README
(`https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/README.md`, read
2026-10-11) and the GitHub API:

- License: MIT. Latest release tag at the query date: `v1.9.5` (2026-10-06). The
  release has **no uploaded binary assets** (empty asset list), so on ARM it must
  be built from source.
- Plain C/C++ implementation without dependencies; the README says Apple Silicon
  is first-class "via ARM NEON, Accelerate framework, Metal and Core ML".
- The supported-platform list includes **Raspberry Pi**, linking to a community
  discussion (`discussions/166`).
- Docker images `ghcr.io/ggml-org/whisper.cpp:main` list `linux/amd64` and
  `linux/arm64` platforms.
- Optional OpenBLAS acceleration: `cmake -B build -DGGML_BLAS=1`.
- Model memory/disk table in the README: tiny 75 MiB disk / ~273 MB memory,
  base 142 MiB / ~388 MB, small 466 MiB / ~852 MB, medium 1.5 GiB / ~2.1 GB,
  large 2.9 GiB / ~3.9 GB.

Cross-reference: the project's own record says a **CPU-only x86 build** of v1.9.4
was verified on 2026-09-30 ([`whisper-cpp.md`](../whisper-cpp.md)). No ARM build
was ever made by V.

**Not verified**: that the v1.9.5 CMake build succeeds on a given ARM board and
compiler; real speed or RAM on a Pi (the README table is not ARM-specific);
that the adapter's required CLI flags match on an ARM build (they are
architecture independent, so it is expected, not verified).

## 6. Not a dependency of V today: KittenTTS stack

The roadmap asks about the dependencies of KittenTTS (spacy, misaki). V does not
list any of them: a search for `kitten` in `pyproject.toml` and `src/` finds
nothing. The table is informational for the planned TTS program, nothing more.

| Package | Linux aarch64 wheel for CPython 3.12? | Source |
|---|---|---|
| kittentts 0.1.3 | `py2.py3-none-any` (pure). Verified. Its hard dependencies per PyPI: `espeakng-loader`, `huggingface-hub`, `numpy`, `onnxruntime`, `phonemizer`, `soundfile`. The relation between this PyPI release and the "KittenTTS 0.8 ONNX" models in the audit is **not verified**. | [PyPI json](https://pypi.org/pypi/kittentts/json) |
| spacy 3.8.16 | Yes: `cp312-cp312-manylinux_2_24_aarch64.manylinux_2_28_aarch64` (also musllinux). Requires Python `<3.15,>=3.9`. Verified. | [PyPI json](https://pypi.org/pypi/spacy/json) |
| misaki 0.9.4 | `py3-none-any` (pure), requires Python `<3.13,>=3.8`. Verified. Its `en` extra adds `spacy`, `espeakng-loader`, `phonemizer-fork`, `num2words`. | [PyPI json](https://pypi.org/pypi/misaki/json) |
| espeakng-loader 0.2.4 | Yes: `py3-none-manylinux_2_28_aarch64`. Verified. | [PyPI json](https://pypi.org/pypi/espeakng-loader/json) |
| soundfile 0.14.0 | Yes: `py2.py3-none-manylinux_2_28_aarch64`. Verified. | [PyPI json](https://pypi.org/pypi/soundfile/json) |
| phonemizer 3.4.0 | `py3-none-any` (pure). Verified. (It drives an espeak backend; the loader above supplies the library.) | [PyPI json](https://pypi.org/pypi/phonemizer/json) |

Warning for the future TTS slice: `misaki` 0.9.4 declares `Python <3.13`. V
requires `>=3.12`. That is compatible with 3.12 only, which matters if V ever moves
to 3.13/3.14. Not verified: the full transitive tree of spacy (thinc, blis,
cymem, ...) on aarch64; only spacy itself was checked.

## 7. Summary matrix

| Piece | Exists for Linux aarch64 + CPython 3.12? | Evidence |
|---|---|---|
| Base: fastapi, uvicorn, alembic, typer | Yes (pure Python) | Verified |
| Base: sqlalchemy, pydantic-core, markupsafe | Yes (aarch64 wheels) | Verified |
| asr-local: faster-whisper, ctranslate2 | Yes | Verified (files); runtime unverified |
| asr-local: onnxruntime, av, tokenizers, hf-xet, pyyaml | Yes | Verified |
| asr-local: nvidia-cublas-cu12, nvidia-cudnn-cu12 | Wheels exist, but pointless on a board without NVIDIA GPU and ~1.35 GB | Existence verified; usefulness not verified |
| diarization: numpy, sherpa-onnx, sherpa-onnx-core | Yes | Verified |
| onnxruntime via sherpa | No dependency; sherpa bundles its own | Verified |
| FFmpeg static aarch64 bundle | Download exists, digest matches, ELF aarch64, but glibc-dynamic | Verified (not executed) |
| whisper.cpp | Source build only; README supports ARM and Raspberry Pi | Verified (README); build on ARM not done |
| KittenTTS stack | Pieces exist; not part of V yet | Verified (files) |

Nothing here shows that V, as a whole, starts or runs acceptably on ARM. What is
unknown and needs hardware: actual install time, memory, thermal behaviour, real-time
factor of each engine, the preload code path on aarch64, the FFmpeg binaries
executing, audio device handling, and the web UI on a small screen. Those belong to
V9-02.

## 8. Changes V would need (list for a future slice, not implemented)

1. **Architecture-aware CUDA markers** in `pyproject.toml`: restrict the
   `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` entries to x86_64
   (for example `platform_machine == 'x86_64' or platform_machine == 'AMD64'`),
   or move them into a separate optional extra such as `asr-cuda`. Decide the
   policy for aarch64 + NVIDIA (SBSA servers) explicitly. `pyproject.toml` and
   `uv.lock` are root-owned files; the lock must be regenerated by root.
2. **Do not preload CUDA libraries on aarch64** unless a GPU is detected:
   skip `_preload_cuda_libraries` when `platform.machine()` is ARM and no
   `nvidia-smi` GPU exists, and make the CPU/int8 default for ARM explicit in the
   hardware profile (`infrastructure/asr/hardware.py`).
3. **Hardware profile for SBCs**: recognise ARM CPUs and small RAM in the
   hardware detection so the model recommendation chooses `tiny`/`base` with int8
   and warns about `medium` and above. Thresholds must come from V9-02
   measurements, not from the README tables.
4. **FFmpeg**: keep the system-FFmpeg-first rule; on Linux arm64 add a clear
   diagnostic when the bundled binary cannot run (musl, old glibc) and tell the
   user to install the distribution package. Consider recording the minimum glibc
   once measured. The `linux_arm64` digest table needs no change today.
5. **whisper.cpp on ARM**: document an ARM build recipe (CMake, optional
   OpenBLAS) in `docs/whisper-cpp.md` after it has been built on real hardware;
   until then it stays "unverified". Check that `whisper_cpp_fallback.py`
   suggests it for low-resource ARM profiles.
6. **CI**: add an aarch64 Linux job (GitHub-hosted arm64 runners or QEMU) that
   at least runs `uv sync --extra diarization --extra asr-local` and the unit
   tests, to catch missing wheels early. Not verified: availability and cost of
   such runners for this repository.
7. **Install docs**: an ARM page stating the exact verified state (what exists,
   what was measured) once V9-02 has real numbers, without compatibility claims
   before that.
8. **TTS stack (future program)**: re-check `misaki`'s `Python <3.13` bound and the
   full spacy tree on aarch64 before choosing a TTS dependency set.

## Sources

- PyPI JSON API, read 2026-10-11: `https://pypi.org/pypi/<package>/json` for
  fastapi, uvicorn, alembic, typer, sqlalchemy, faster-whisper, ctranslate2,
  nvidia-cublas-cu12, nvidia-cudnn-cu12, numpy, sherpa-onnx, sherpa-onnx-core,
  onnxruntime, kittentts, spacy, misaki, espeakng-loader, soundfile, phonemizer.
- Locked versions and wheel lists: [`uv.lock`](../../uv.lock) in this repository.
- FFmpeg bundle: `https://github.com/zackees/ffmpeg_bins` at commit
  `df95abcb0ce6efff710dda5ef28a2f6f1dc21493`, file `v8.0/linux_arm64.zip`.
- whisper.cpp: `https://github.com/ggml-org/whisper.cpp` (README on master and the
  GitHub releases API, read 2026-10-11).
