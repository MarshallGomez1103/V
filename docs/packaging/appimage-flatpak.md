# AppImage and Flatpak: measured prototypes (S15.12, S15.13)

Status: **experimental prototypes, not published or supported**. The current
recipes use the V brand. Packaging unit tests exercise staging and command
forwarding with local tool substitutes. A separate local check of the current
wheel, standalone CPython AppDir, complete base AppImage and uninstalled
Flatpak bundle is described below. Direct FUSE launch remains pending.
Native Windows/macOS launcher verification is also pending.

The historical measurements describe the **2026-09-30 builds**, before the rename,
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
Flatpak commands: Flatpak needs a dedicated sandbox harness. The separate local
check below uses disposable sandbox storage without installing the application.

Both scripts work in `VOZ_WORK` (a `mktemp -d` by default; never the repo), start
from `git archive HEAD` if not given a wheel, and need network access (PyPI, uv's
standalone CPython, `appimagetool`, the `org.flatpak.Builder` extension and the
`--user` SDK). Flatpak uses `io.github.marshallgomez1103.v`; this is the
application identifier, not a website or network address. Artifact names use
`V-*`; the Python package,
distribution and `VOZ_*` environment variables retain their compatibility names
([ADR-0009](../adr/0009-rename-to-v.md)). The Flatpak build produces a bundle
without installing it into the host's user installation.

## Current base package checks (2026-10-21)

The working-tree wheel based on `dd7158f`, including the current README and
frontend, was assembled with existing local components. No dependencies were
resolved and no engine extras or model weights were included. These checks did
not execute the online recipes end to end. The base payload contains the
application and 24 third-party Python distributions.

| Observation | AppImage | Flatpak |
| --- | --- | --- |
| Artifact | `V-0.1.0-x86_64.AppImage`, 36,596,216 B | `V-0.1.0-x86_64.flatpak`, 7,320,640 B |
| Python | Standalone CPython 3.12.14 | CPython 3.13 in existing Freedesktop Platform 25.08 |
| Construction | Exit 0 in 7.48 s | Bundle export exit 0; bundle construction exit 0 in 10.64 s |
| Independent HTTP smoke | Health, UI and three license files returned 200 in 2.01 s | The imported bundle checkout returned the same responses in 1.67 s |
| Shutdown | HTTP 202, application exit 0, no surviving process group | HTTP 202, application exit 0, no surviving process group |
| Payload inventory | 6,086 entries: 4,739 files, 1,049 symlinks, 298 directories | 2,056 entries: 1,862 files, 194 directories, no symlinks |
| FFmpeg | Uses the host executable | Uses the existing Platform runtime |

The wheel is `voz_transcriber-0.1.0-py3-none-any.whl`, **1,098,115 B**.
All 277 package files, including 50 static web files, match the source checkout;
296 wheel RECORD entries and its embedded README were checked. Both payloads
preserve the three original font/JavaScript notice files exactly. No personal
host path or private-plan reference was identified in their contents, and all
AppDir symlinks stay within the payload.

Both base payloads contain Mako 1.4.2. The AppImage excludes unused pip entry
points, its package metadata and ensurepip, including their vendored CA bundles;
the original runtime is preserved and `pipes.py` remains present. Installation
into the target uses external uv rather than embedded pip. The workspace's
separate certifi/Vite security updates and advisory-query limits are documented
in the [security audit](../security/pre-release-audit.md).

Construction, extraction and smoke steps each used a 60 s deadline, two logical
CPUs, temporary HOME/XDG directories and an outer network namespace with local
loopback only. The source checkout and existing Flatpak user installation were
read-only. The Flatpak application was **not installed**: its bundle was imported
into a disposable OSTree repository, checked out, compared with staging and
launched from that checkout. Exported content and executable bits match; OSTree
normalizes three dependency RECORD files from mode 0664 to 0644 without changing
their bytes. The exported commit contains no smoke-test state.

The standalone runtime's build-prefix metadata is relative to its running
prefix in this artifact; that adjustment remains outside the current recipe.
SquashFS omits extended attributes (`-no-xattrs`), and extracted bytes, modes
and symlink targets match the staged AppDir.

| Component | SHA-256 |
| --- | --- |
| Wheel | `9e18a44069fce0f9e7c8ed714aed7243d68ed860106ba12f309a36f9ab345911` |
| AppImage | `9fba063ead1a7a9189eff85dc4738f5e495c48c30b0a6ca8c910c2791269dd99` |
| Flatpak bundle | `51b6ba10cf7d5eb463bfc58c0c86167904b8ac061d8815c1ccc153c7f52ad238` |
| Official `appimagetool-x86_64.AppImage` input | `95cbe7cce9717fce90c484e34052ee7c7f1d7635b33c12525b4776826a7d29b6` |
| Official `runtime-x86_64` input | `617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46` |

Tool provenance: [appimagetool release](https://github.com/AppImage/appimagetool/releases/tag/continuous),
commit `854e19e951900cf141245b384d45735942521abe`, asset `610035789`;
[type-2 runtime release](https://github.com/AppImage/type2-runtime/releases/tag/continuous),
commit `fedfad51acc2860b2916a1eef32ba4a500ff31ef`, asset `657374641`.
Mutable release URLs require checking these input hashes. Supplying
`--runtime-file` kept construction offline; the embedded runtime differs only
within the ELF `.digest_md5` section written by appimagetool.

The actual AppImage launch used extraction rather than FUSE:

```bash
packaging/common/smoke.sh ./V-0.1.0-x86_64.AppImage --appimage-extract-and-run
```

These individual Linux x86-64 checks are not a startup benchmark. They exercise
HTTP serving and shutdown, without transcription, synthesis, diarization, GPU
inference, desktop browser launch, direct FUSE mounting or native Windows/macOS
launches. No application package was installed or published. Voice-engine
extras and models must be supplied separately; these base checks do not validate
an inference-enabled portable distribution.

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
AppImage has no such restriction: it uses the host driver directly. The
historical `asr-local` variants shipped CUDA 12 wheels and depended on a
compatible host driver. The current base packages contain no CUDA engine extras;
their HTTP smoke checks do not establish GPU inference support.

**Reproducibility and Flathub.** The manifest resolves PyPI dependencies at build
time with `--share=network` (marked `ponytail:` in the manifest). Flathub requires
pinned sources and offline builds: one module per wheel would have to be generated
(`flatpak-pip-generator`) with hashes. For the ASR extra that is ~1 GB of sources.
`flatpak-builder-lint` remains unverified. The metainfo passes
`appstreamcli validate --no-net`; it reports two informational notices for the
missing content rating and developer name. This metadata check does not validate
the complete Flatpak build or runtime.

**AppImage.** It requires FUSE 2 to run directly; the standalone CPython is
self-contained, but manylinux wheels depend on the host's glibc. The AppImage is
neither updated nor signed. `AppRun` does not define `PYTHONHOME`: the standalone
CPython locates its stdlib relative to its binary.

## Recommendation

Keep `uv tool install` ([Linux installation](../install/linux.md)) as the supported
path. The current base AppImage and Flatpak remain experimental downloads until
their intended inference extras and native launch paths are exercised. AppImage
uses host FFmpeg; Flatpak provides Python/FFmpeg but keeps a separate data
namespace and still needs a reproducible, pinned-source manifest for Flathub.

Before distributing either format, verify its complete dependency/license
closure, add an isolated smoke to the release workflow and test the selected
engine/model combinations. Runtime probing alone does not establish inference
compatibility. Redistributing FFmpeg or weights also requires their own notices
and applicable redistribution terms.
