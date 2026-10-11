# Installing on Windows and macOS

V (formerly VOZ) keeps the `voz` data directory names; `v` and `voz` are the same command (`v` since slice V1-02; an installation made before that only has `voz` until it is reinstalled or `uv sync` runs). See [ADR-0009](../adr/0009-rename-to-v.md).

> **Verification status.** V has only been used by hand on Linux (Bazzite). The
> code has Windows- and macOS-specific paths, and its CI (`Backend /
> windows-latest` and `macos-latest`) runs the whole test suite and starts the
> real server, but until someone uses it on a real machine it **is experimental**.
> If something fails, open an issue with the output of `voz doctor --redact`. See
> also [Troubleshooting](../troubleshooting.md).

## Requirements

- [`uv`](https://docs.astral.sh/uv/) (it downloads the right Python by itself;
  the repository pins Python **3.12** in `.python-version`).
- Windows 10/11 x86-64, or macOS 13 or later (Apple Silicon; Intel works with
  Python 3.12/3.13).
- Nothing else: FFmpeg is obtained automatically (below).

From a checkout, the equivalent of "clone and double-click" is:

```bash
uv run --extra asr-local --extra diarization voz
```

## Automatic FFmpeg

V needs `ffmpeg` and `ffprobe`. If they are not on the `PATH`, at startup it
downloads, **once** (about 40-140 MB depending on the system), a static build from
the `zackees/ffmpeg_bins` repository, pinned to a commit and verified with
SHA-256, into V's cache folder (`…/cache/ffmpeg/`). It does not use the
`static-ffmpeg` package (it pulls in `twine` and about 25 dependencies and
downloads without checksums). An already installed FFmpeg always takes priority.
Without network access, `voz doctor` tells you how to install it by hand
(`winget install ffmpeg`, `brew install ffmpeg`). To disable the download, set
the environment variable `VOZ_FFMPEG_AUTO_DOWNLOAD=0`.

## GPU

- **Windows with NVIDIA**: the `asr-local` extra includes `nvidia-cublas-cu12`
  and `nvidia-cudnn-cu12` (about 1.3 GB of wheels). V registers their DLLs before
  loading CTranslate2. If CUDA does not load, V falls back to the CPU (int8) with
  a warning and the job never fails because of it. You need the NVIDIA driver
  (not the CUDA Toolkit).
- **macOS**: always CPU (int8); there is no CUDA.

## Where V stores its data

| Content | Windows | macOS |
| --- | --- | --- |
| Configuration | `%LOCALAPPDATA%\voz\config` | `~/Library/Application Support/voz/config` |
| Data (SQLite database, projects, models) | `%LOCALAPPDATA%\voz\data` | `~/Library/Application Support/voz/data` |
| Cache (FFmpeg, waveforms) | `%LOCALAPPDATA%\voz\cache` | `~/Library/Caches/voz` |
| State and backups | `%LOCALAPPDATA%\voz\state` | `~/Library/Application Support/voz/state` |

An absolute `XDG_*_HOME` variable replaces the corresponding folder on any
system (useful for tests or portable installs).

## Guarantees weaker than on Linux/macOS

- **Windows has no `dir_fd`.** On Linux and macOS, originals and derived files
  are opened relative to a directory descriptor without following symbolic links.
  On Windows every path component is checked with `lstat` (rejecting links and
  junctions) before use, but a race window remains that `dir_fd` closes. Writing
  is still atomic (copy to a temporary file + hard link without replacement) and
  the original stays read-only and is never modified. NTFS is required (hard
  links).
- Windows has no POSIX modes: the API key file (`secrets.toml`) is protected by
  the user profile's permissions instead of `0600`, and the mode is not checked
  when reading it.
- Directory `fsync` does not exist on Windows (NTFS covers it with its journal).
- The peak-memory figure of `voz bench` does not count child processes on
  Windows.
