# Plan: V as a desktop application with Tauri

Status: **plan, nothing implemented**. Today V is opened with a double-click
launcher (`Iniciar-*`) that starts the local server and opens the browser. This
document describes how to package it as an installable application (own window,
icon, per-system installer) with [Tauri 2](https://v2.tauri.app), what it costs
and what risks it has.

## What the user gains

- An installer per system (`.msi`/`.exe` on Windows, `.dmg` on macOS,
  `.AppImage`/`.deb`/`.rpm` on Linux) instead of cloning the repo.
- A window of its own without the browser bar, an icon in the dock/taskbar and in
  the applications menu.
- Closing the window closes V: no orphaned server or open terminal remains.
- Updates from within the app (`updater` plugin).

## Proposed architecture

```text
┌──────────── Tauri (Rust, ~10 MB) ─────────────┐
│  WebView window ── loads http://127.0.0.1:P   │
│  lifecycle: start / watch / close             │
└───────────────┬───────────────────────────────┘
                │ sidecar (child process)
┌───────────────▼───────────────────────────────┐
│  V server (Python: FastAPI + jobs + ASR)      │
│  the same as today, no domain changes         │
└───────────────────────────────────────────────┘
```

The backend stays Python: Faster Whisper, CTranslate2 and sherpa-onnx have no
reasonable Rust equivalent, and rewriting them gains nothing. Tauri is only the
shell. The React/Carbon UI is reused as is.

### Lifecycle

1. Tauri picks a free port and a random token and starts the sidecar:
   `voz serve --no-browser --port P` with `VOZ_DESKTOP_TOKEN=<token>`.
2. It shows a loading screen of its own while polling `/api/health` (today it
   takes ~1 s; the first time it includes the database migration).
3. It navigates the window to `http://127.0.0.1:P`.
4. When the window closes: `POST /api/shutdown` (it already exists for the Close
   server button); if it has not finished within 5 s, it kills the process. A job
   in progress stays recoverable, as today with Ctrl+C.
5. `single-instance` plugin: a second double-click focuses the existing window
   (today the CLI already reuses the open server).
6. If the sidecar dies, the window shows "V stopped" with a Restart button and the
   end of the log.

### Security

- The server only listens on `127.0.0.1`, as today.
- The token from step 1 is required on the dangerous routes (`/api/shutdown`,
  cloud keys), in addition to the current anti-CSRF header; this way another web
  page open in the user's browser cannot shut V down or read keys.
- Tauri CSP limited to `127.0.0.1:P`; no `shell` open to the web.

## The big problem: Python and heavy dependencies

| Piece | Approximate size |
| --- | --- |
| Tauri shell | ~10 MB |
| Standalone CPython + V + FastAPI | ~50 MB (measured in the base AppImage: 46 MiB) |
| faster-whisper + CTranslate2 + onnxruntime + sherpa-onnx | ~250 MB |
| CUDA wheels (cuBLAS + cuDNN, Windows/Linux with NVIDIA only) | ~1.3 GB compressed, 2.2 GB installed |
| Static FFmpeg | ~50–70 MB |
| Whisper models (turbo ~1.6 GB, large-v3 ~3 GB) | downloaded inside the app |

Three ways to carry Python, from least to most work:

1. **"uv" sidecar (recommended to start)**: the installer carries `uv` (a ~30 MB
   binary) and V's code with its `uv.lock`. On first launch, `uv sync` downloads
   Python and the dependencies into the app's data folder, with a progress
   screen. This is exactly what the launchers do today, so it is proven on the
   three systems by CI. Small installer (~50 MB); the first launch needs Internet.
2. **Frozen Python (PyInstaller/Nuitka) as a sidecar**: one executable per system
   with everything inside except CUDA and models. A ~300–400 MB installer; it
   works offline except for the models. Maintaining the CTranslate2/onnxruntime
   hooks and signing many binaries is costly.
3. **Everything inside, including CUDA**: a ~1.5 GB installer. Not worth it: most
   machines have no NVIDIA, and those that do can download it later.

In all three, CUDA is downloaded separately and only if there is an NVIDIA GPU
(`nvidia-smi` present), and models are still downloaded from the model manager.

## Signatures and system warnings

- **Windows**: unsigned, SmartScreen warns "Windows protected your PC". A
  code-signing certificate costs ~100–400 USD/year (or Azure Trusted Signing,
  cheaper). Defender may flag the downloaded FFmpeg or the sidecar; signing
  reduces that.
- **macOS**: without signing and notarizing, Gatekeeper blocks the app. It needs
  an Apple Developer account (99 USD/year). Every binary inside (sidecar, Python's
  `.so`/`.dylib`, FFmpeg) must be signed; with option 1, what `uv` downloads on
  first launch is not signed by us: it must be checked that Gatekeeper allows it
  (PyPI wheels are usually fine; the downloaded FFmpeg must be tested).
- **Linux**: AppImage, `.deb` and `.rpm` need no mandatory signature. On
  Bazzite/Fedora Atomic the natural fit is AppImage or Flatpak (measured
  prototypes already exist in [appimage-flatpak.md](appimage-flatpak.md)).

## Concrete risks

- **Different WebView per system**: Tauri uses WebView2 (Windows, Chromium),
  WKWebView (macOS, Safari) and WebKitGTK (Linux). The UI is only tested in
  Chrome today. Main risk: **playing AAC/M4A audio in WebKitGTK** depends on the
  system's GStreamer plugins. Mitigation: have the player use the normalized
  WAV/derivative that V already generates, or serve transcoded audio.
- **Cold start** of option 1: the first time it takes minutes. It needs an honest
  progress screen (what is downloading, how much is left).
- **Antivirus and long paths on Windows**: a deep `.venv` inside
  `%LOCALAPPDATA%`; watch the 260-character limit.
- **Two copies of the truth**: the `Iniciar-*` launchers and the app must share
  the same data folder (already solved by `paths.py`) so a user can switch from
  one to the other without losing projects.

## Phases and estimated effort

| Phase | What | Effort |
| --- | --- | --- |
| 0 | **Installable app without Tauri**: a PWA manifest so Chrome/Edge offer "Install V" (own window and icon) on top of the current local server | 1 afternoon |
| 1 | Tauri shell in `apps/desktop/`: window, `uv` sidecar (option 1), loading screen, clean shutdown, single-instance, token | 3–5 days |
| 2 | Guided first launch: `uv sync` progress, NVIDIA detection and optional CUDA, clear errors without Internet | 2–3 days |
| 3 | CI with `tauri-action` on Windows, macOS and Linux that builds unsigned installers and runs a smoke test (open, `/api/health`, close) | 2 days |
| 4 | Signing and notarization (requires buying certificates), updater with GitHub releases | 2–3 days + paperwork |
| 5 | Optional: frozen Python (option 2) to install without Internet | 1–2 weeks |

Recommendation: do phase 0 now (almost free, gives the "application" effect on
Windows, macOS and Linux) and phases 1–3 when publishing is wanted. Signing
(phase 4) only makes sense with the public release.

## What does not change

- The domain, the API and the UI. Tauri does not require touching the backend
  except for the optional token in the security section.
- The `Iniciar-*` launchers remain the way to use V from source and the
  development path.
