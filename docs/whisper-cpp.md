# whisper.cpp as an alternative local provider

Adapter: `src/voz/infrastructure/asr/whisper_cpp.py` (`provider_id = "whisper-cpp"`),
catalog: `whisper_cpp_catalog.py`, suggestion policy:
`src/voz/application/whisper_cpp_fallback.py`. Roadmap section 9 (S9.01–S9.09).

> **Verification status.** The adapter, the detection and the catalog are tested
> with a **fake** executable (`tests/fixtures/whisper_cpp/fake_whisper_cli.py`)
> that imitates the CLI and writes the JSON. 2026-09-30: a **CPU-only** build was
> verified with whisper.cpp v1.9.4 (`uvx cmake`, GCC 16.2.1); the real `-ojf` JSON
> matches the adapter (fixture `tests/fixtures/whisper_cpp/real_ojf_v1.9.4.json`).
> CPU/GPU benchmark (S9.10) in [benchmarks.md](benchmarks.md). CUDA/Vulkan are
> unverified.

## How V finds the executable

1. If `VOZ_WHISPER_CPP_BIN` is defined, **only** that path is used (it must be an
   executable file). An invalid path does not silently fall back to the `PATH`.
2. Otherwise, `whisper-cli` is looked up in the `PATH`.

Validation (`probe_whisper_cpp`) runs `whisper-cli --help` without a shell and with
a timeout, and requires the flags `--model --file --language --output-json-full
--output-file --no-gpu --no-prints --offset-t --duration` (whisper.cpp >= 1.7).
The typed result is `WhisperCppAvailability(available, reason, version)`; the
reasons are stable codes without paths: `whisper_cpp_not_found`,
`whisper_cpp_not_executable`, `whisper_cpp_probe_timeout`,
`whisper_cpp_missing_flags`. The version is reported only if `--help` prints it.

## Building with CUDA (NVIDIA)

It requires the CUDA Toolkit and a GCC compatible with it (on Fedora/Bazzite the
system GCC is usually too new: build inside a toolbox/distrobox).

```bash
# Bazzite (immutable system): mutable environment for building
toolbox create whispercpp && toolbox enter whispercpp
sudo dnf install -y git cmake gcc-c++ make
# CUDA Toolkit: NVIDIA's official repository for Fedora, then
#   sudo dnf install cuda-toolkit
git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp
git checkout v1.9.4   # verified tag (CPU only); 5359861c… is the revision of the models repo on HF, not of this repo
cmake -B build -DGGML_CUDA=1
cmake --build build -j --config Release
# binary: build/bin/whisper-cli
```

CPU-only without a toolbox (verified): `uvx cmake -B build && uvx cmake --build build -j --config Release`.
Alternative: `brew install cmake` (Homebrew on Bazzite) for cmake, but the CUDA
toolkit and the compatible compiler are still needed.

## Building with Vulkan (AMD/Intel/NVIDIA without CUDA)

```bash
toolbox create whispercpp && toolbox enter whispercpp
sudo dnf install -y git cmake gcc-c++ make \
  vulkan-headers vulkan-loader-devel glslc shaderc
git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp
cmake -B build -DGGML_VULKAN=1
cmake --build build -j --config Release
```

Check the driver with `vulkaninfo --summary` (package `vulkan-tools`) before
blaming the build. Without either flag the build is CPU-only.

## Pointing V at the binary

```bash
export VOZ_WHISPER_CPP_BIN="$HOME/src/whisper.cpp/build/bin/whisper-cli"
```

If the binary runs from a toolbox, the `$HOME` path is the same inside and outside
the container; the toolbox's CUDA/Vulkan libraries may not exist on the host, in
which case copy the static build or export `LD_LIBRARY_PATH` before starting V.

## Quantized models (S9.05)

Repo `ggerganov/whisper.cpp`, revision `5359861c739e955e79d9a303bcbc70fb988958b1`
(MIT). One `ggml-<model_id>.bin` file per model, with fixed size and SHA-256; they
are installed with `FileSystemModelStore.download` (resumable, verified, atomic
publication) and **never** without an explicit request.

| model_id | file | size (bytes) |
| --- | --- | --- |
| `large-v3-turbo-q5_0` | `ggml-large-v3-turbo-q5_0.bin` | 574,041,195 |
| `large-v3-turbo-q8_0` | `ggml-large-v3-turbo-q8_0.bin` | 874,188,075 |
| `large-v3-turbo` | `ggml-large-v3-turbo.bin` | 1,624,555,275 |
| `small-q5_1` | `ggml-small-q5_1.bin` | 190,085,487 |
| `small` | `ggml-small.bin` | 487,601,967 |
| `base` | `ggml-base.bin` | 147,951,465 |

## Adapter contract

- Command (argument list, no shell): `whisper-cli --model <ggml> --file <wav>
  --language <code|auto> --output-json-full --output-file <base> --no-prints
  [--no-gpu] [--offset-t <ms> --duration <ms>]`. The language is the primary
  subtag (`es-CO` -> `es`); `None` -> `auto`. `--no-gpu` only with
  `force_cpu=True`. The clip of a recoverable invocation is passed with
  `--offset-t/--duration`; the JSON times are global, as in Faster Whisper.
- The audio is copied to a private temporary directory (0700) that is always
  removed; it is validated to be 16 kHz mono 16-bit PCM WAV before launching the
  process (otherwise `transcription_invalid_audio`).
- Segments: `transcription[].offsets.from/to` (ms) and `text`. Padding is
  stripped but the leading word-boundary space is kept (so
  `TranscriptionResult.text` still joins with `"".join`); empty ones are
  discarded and overlaps of a few ms are trimmed to keep the order.
- Words (if `word_timestamps`): tokens are grouped into words (a leading space
  opens a word; `[_BEG_]`, `[_TT_..]` are ignored); the probability is the mean of
  `p`. If some token has no valid offsets, the segment ends up with no words (the
  text is not lost). `t_dtw` is ignored for now.
- Failures (all with a message free of paths): missing or non-executable binary,
  exit code != 0 and unreadable/incomplete JSON -> `transcription_provider_failed`;
  missing model file -> `transcription_model_not_installed`.
- Cancellation: the token is polled every 100 ms; on cancellation `terminate()` is
  called (and `kill()` after 2 s) and `transcription_cancelled` is raised. The
  process is never orphaned and leaves no temporary files.

## Provider suggestion (S9.09)

`suggest_whisper_cpp(faster_whisper=RuntimeAvailability, whisper_cpp_available=bool)`
is a pure function: it returns `ProviderSuggestion("whisper-cpp", reason)` with
`faster_whisper_runtime_missing` or `faster_whisper_no_cuda`, or `None`. It never
switches provider on its own (the UI shows it and the user chooses), never
proposes a cloud provider and suggests nothing if the hardware is unknown.
