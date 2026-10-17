# AppImage and Flatpak: measured prototypes (S15.12, S15.13)

Status: **experimental prototypes, not published or supported**. The current
recipes use the V brand. Packaging tests exercise staging and command forwarding
with local tool substitutes; they do not build or run an AppImage or Flatpak.
A real wheel extracted into an AppDir was also started with the existing Python
environment: `/api/health` and `/` returned 200 and API shutdown exited with 0.
This does not verify standalone CPython, FUSE or a complete AppImage.
Native Windows/macOS launcher verification is also pending.

The measurements below describe the **2026-09-30 builds**, before the rename,
on Bazzite (Fedora Atomic) x86-64 with an RTX 4060 Laptop and wheel
`voz_transcriber-0.1.0`. They are not measurements of the current recipes.
There is no CI for these formats.

Reproducible recipes in `packaging/`:

| File | Purpose |
| --- | --- |
| `packaging/appimage/build.sh`, `AppRun` | AppImage: standalone CPython (uv) + wheel + dependencies in `usr/lib/voz` |
| `packaging/flatpak/build.sh`, `io.github.marshallgomez1103.v.yml`, `io.github.marshallgomez1103.v.metainfo.xml` | Flatpak on `org.freedesktop.Platform//25.08` |
| `packaging/common/smoke.sh` | Starts the package with `--no-browser`, measures the time to `/api/health` 200, checks `/` and requests graceful shutdown |
| `packaging/common/v.desktop`, `v.svg` | Shared launcher and icon |

```bash
packaging/appimage/build.sh [wheel]            # VOZ_EXTRAS=asr-local, VOZ_FFMPEG_DIR=<dir with static ffmpeg/ffprobe>
packaging/flatpak/build.sh [wheel]             # VOZ_EXTRAS=asr-local; builds without installing
packaging/common/smoke.sh ./V-0.1.0-x86_64.AppImage
```

`smoke.sh` gives the child a temporary HOME and XDG directories, checks both
HTTP endpoints, requests `POST /api/shutdown` with the action header and requires
HTTP 202 plus exit 0 within a deadline. Signals clean up failed runs. It rejects
Flatpak commands: a sandbox launch with disposable storage has not been verified.

Both scripts work in `VOZ_WORK` (a `mktemp -d` by default; never the repo), start
from `git archive HEAD` if not given a wheel, and need network access (PyPI, uv's
standalone CPython, `appimagetool`, the `org.flatpak.Builder` extension and the
`--user` SDK). Flatpak uses `io.github.marshallgomez1103.v`; this is the
application identifier, not a website or network address. Artifact names use
`V-*`; the Python package,
distribution and `VOZ_*` environment variables retain their compatibility names
([ADR-0009](../adr/0009-rename-to-v.md)). The Flatpak build produces a bundle
without installing it into the host's user installation.

## Historical measured results (2026-09-30)

Startup = process launched with empty XDG directories until `/api/health` 200
(database migration included), 3 repetitions per variant where indicated.

| Variant | Artifact | Installed | Build | Startup to `/api/health` |
| --- | --- | --- | --- | --- |
| AppImage base (host FFmpeg) | 46 MiB (48,450,040 B) | 171 MB (AppDir) | 8–9 s with an empty uv cache | 0.93 / 1.11 / 0.94 s |
| AppImage base + static FFmpeg | 98 MiB (102,742,520 B) | | 7 s (+ 42 MB download) | 1.11 s |
| AppImage `asr-local` | 1.42 GiB (1,525,004,792 B) | 4.3 GB (AppDir + work) | 192 s (166 s of dependencies) with an empty uv cache | 1.23 / 1.27 s |
| Flatpak base | 11 MB (bundle, 11,565,320 B) | 52.6 MB | 111 s | 1.05 / 0.70 / 0.69 s |
| Flatpak `asr-local` | 1.06 GB (bundle, 1,059,718,376 B) | 2.8 GB | 7.3 min `flatpak-builder` + ~14 min of `build-bundle` | 0.66 s |

Measurement notes: the Flatpak base variant's times include downloading the wheels
from PyPI; the AppImage reuses the same CPython. `build-bundle` takes very long in
the ASR variant because of ostree compression; for local use it is not needed
(`flatpak-builder --install` is enough).

### What was checked in each format

- `voz doctor --json` inside the package: FFmpeg `ok`, writable paths, `ASR
  runtime ok faster-whisper available` and `GPU/CUDA ok CUDA: float16, int8,
  int8_float16` in **both** `asr-local` variants (pip's cuBLAS/cuDNN ship inside:
  `nvidia/` weighs 2.2 GB and is the bulk of the size).
- Clean stop: the AppImage exits with 0 after SIGINT. `flatpak run` returns 130
  (the SIGINT also reaches the `flatpak run` wrapper); the server stops.
- No audio was transcribed and no model was downloaded (rules of the wave).
- **Not** tested: opening the browser from the `.desktop` launcher (the smoke
  tests use `--no-browser`), running on other distributions, AppImage without FUSE
  (`--appimage-extract-and-run` is the alternative), aarch64.

## FFmpeg

- **AppImage**: `AppRun` prepends `usr/bin` to the `PATH`. Without
  `VOZ_FFMPEG_DIR` it uses the host's FFmpeg (on Bazzite, the system's or
  Distrobox's; if missing, `voz doctor` warns and the UI starts anyway). With
  static binaries from johnvansickle.com (7.0.2, ~77 MB each) the AppImage grows
  52 MiB compressed and `voz doctor` reports `ffmpeg version 7.0.2-static`. Those
  binaries are **GPLv3**: redistributing them requires including their license and
  the source offer, so they are not included by default.
- **Flatpak**: nothing is needed; runtime 25.08 ships `/usr/bin/ffmpeg` and
  `ffprobe` (7.1.3) and CPython 3.13, and the wheel (`requires-python >=3.12`) is
  installed with the SDK's `pip3` into `/app`. Patent-encumbered codecs would
  depend on the `ffmpeg-full` extension (not tested with real media).

## Problems and limits

**Sandbox and network.** The server listens on `127.0.0.1` inside the sandbox.
Without `--share=network` the sandbox's loopback is a different one and the host's
browser cannot reach it: this was checked with `flatpak run --unshare=network`
(the server starts and `/api/health` does not answer from outside). The app
declares `--share=network`, which also enables the cloud providers only if the
user chooses them; it still listens on `127.0.0.1`, but the sandbox no longer
isolates the network.

**XDG.** V already honors XDG. Flatpak sets `XDG_*` to `~/.var/app/io.github.marshallgomez1103.v/`:
the data (database, projects, multi-GB models) ends up **separate** from that of
`uv tool install` and is not shared. The AppImage uses the host's normal XDG
paths, that is, the same data as a `uv` install. Originals are uploaded from the
browser, so filesystem access is not requested. The old prototype used
`dev.voz.Voz`, which has a separate Flatpak data namespace. There is no automatic
migration or deletion of either namespace.

**GPU/CUDA.** In Flatpak, `--device=all` is needed (`/dev/nvidia*`;
`--device=dri` is not enough) along with the
`org.freedesktop.Platform.GL.nvidia-<version>` extension matching the host
driver (already present on Bazzite). With `--nodevice=all`, `voz doctor` falls to
`CPU only (int8)`. `--device=all` weakens the sandbox and Flathub reviews it. The
AppImage has no such restriction: it uses the host driver directly. Both ship CUDA
12 through wheels, so they depend on the host driver being compatible.

**Reproducibility and Flathub.** The manifest resolves PyPI dependencies at build
time with `--share=network` (marked `ponytail:` in the manifest). Flathub requires
pinned sources and offline builds: one module per wheel would have to be generated
(`flatpak-pip-generator`) with hashes. For the ASR extra that is ~1 GB of sources.
`flatpak-builder-lint` and the metainfo against `appstreamcli` were not verified
either.

**AppImage.** It requires FUSE 2 to run directly; the standalone CPython is
self-contained, but manylinux wheels depend on the host's glibc. The AppImage is
neither updated nor signed. `AppRun` does not define `PYTHONHOME`: the standalone
CPython locates its stdlib relative to its binary.

## Recommendation

1. Keep `uv tool install` ([docs/install/linux.md](../install/linux.md)) as the
   supported path.
2. If a downloadable binary is wanted, **start with the base AppImage** (46 MiB,
   8 s build, ~1 s startup, no network at runtime, GPU without special
   permissions) with the host's FFmpeg and `voz doctor` as the guide. It is the
   format with the fewest moving parts and already reproduces the behavior of
   `uv tool install`. The `asr-local` variant (1.4 GiB) only as a separate
   download labeled experimental, until it is exercised on a real GPU with a
   model.
3. Leave Flatpak for later: it fits Bazzite and brings Python/FFmpeg, but it
   requires `--share=network` and `--device=all`, separate data, and rewriting the
   manifest for Flathub (pinned sources, real ID, `flatpak-builder-lint`).
4. Before publishing either: add it to the release workflow (`release-dry-run`)
   only when there is a smoke test in CI (the base AppImage can do it, without a
   GPU), and record the GPL license if FFmpeg is distributed.
