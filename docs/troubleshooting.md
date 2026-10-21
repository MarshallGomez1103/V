# Troubleshooting

Known problems and their fixes for V. Every case here comes from
the project's own documentation or from the messages the code emits; if yours is
not listed, run the diagnostics and open an issue with the result:

```bash
voz doctor --redact                 # text report, absolute paths hidden
voz doctor --bundle doctor.zip      # redacted zip to attach to a report
```

`v` and `voz` are the same command (`v` since slice V1-02; an installation made before that only has `voz` until it is reinstalled or `uv sync` runs); see [ADR-0009](adr/0009-rename-to-v.md). Examples use `voz`. See [Diagnostics](diagnostics.md)
for what each check means and what the bundle contains. Data directories keep the
name `voz/` (for example `~/.local/share/voz/`).

## Starting V

### `voz: command not found` (Linux)

`uv tool install` links `voz` into `~/.local/bin`. Add it to your `PATH` with
`uv tool update-shell` and open a new terminal.
([Linux](install/linux.md#common-problems))

### The port is busy

`voz doctor` reports `puerto ... ocupado; posiblemente VOZ ya está corriendo` (port
busy, V may already be running). If V is already serving on that address, running
`voz` again does not start a second server: it prints that V is already open and
opens another browser tab. If something else uses the port, start V on another
one: `voz --port 9000`.

### Windows: "Windows protected your PC"

Click *More info -> Run anyway*.
([README](../README.md))

### macOS: "cannot be opened"

Right-click the launcher file and choose *Open*. If the option does not appear:
*System Settings -> Privacy & Security -> Open Anyway*. ([README](../README.md))

### Windows: "path too long"

Move the folder to a short location, for example `C:\Voz`, and open the launcher
again. ([README](../README.md))

### The launcher cannot install `uv`

The launcher installs `uv` the first time and needs an internet connection. If it
reports that it could not install it, check your connection and open the file
again. Any other failure ends with "Algo falló" (something failed): read the
message above it, then open the launcher again. (The launchers are
`Start-V-Windows.bat`, `Start-V-macOS.command` and `start-v-linux.sh`.)

## Requests rejected with 400 `host_not_allowed`

V checks the `Host` header of every request (any port is accepted, only the name
matters) to block DNS-rebinding attacks. A request whose `Host` is not allowed
gets `400` with `{"detail": {"code": "host_not_allowed", ...}}`. Always allowed:
`127.0.0.1`, `localhost`, `::1`, the address passed with `--host`, and every name
passed with `--allow-host`. With a wildcard bind (`--host 0.0.0.0` or `::`), this
machine's own host name and IP addresses are also allowed.

If you reach V under another name (a DNS alias, a reverse proxy, another
machine's name), add it explicitly; the option is repeatable:

```bash
voz --host 0.0.0.0 --auth-token-file ../v-server-token.txt --allow-host my-pc.local --allow-host my-pc
```

Reason: [ADR-0006](adr/0006-local-first-privacy.md).

## Warning when using `--host`

If the bind address is not loopback (`127.0.0.1`, `::1`, `localhost`), `voz`
prints to stderr that V is listening beyond this machine. That is expected, not an
error. A non-loopback bind requires `--auth-token-file`; create the file first
with `v auth-token --output ../v-server-token.txt`. Credentials protect access
but HTTP does not encrypt traffic. See [authentication](api/authentication.md),
or return to the default (`127.0.0.1`).

## FFmpeg

- **`ffmpeg` / `ffprobe` fail in `voz doctor`**: neither was found on the `PATH`.
  At startup V downloads a pinned static build once if it can; otherwise install
  it yourself (`winget install ffmpeg`, `brew install ffmpeg`, or your
  distribution's package manager; on Bazzite, inside a Distrobox container).
  Importing audio will not work until it is installed.
- **No network, or you do not want the download**: set
  `VOZ_FFMPEG_AUTO_DOWNLOAD=0` and install FFmpeg by hand.
  ([Windows and macOS](install/windows-macos.md#automatic-ffmpeg))

## Transcription runtime and speed

- **`voz doctor` warns that `asr-local` is not installed**: Faster Whisper is an
  optional extra. Reinstall with it
  (`uv tool install --force "voz-transcriber[asr-local] @ ./dist/voz_transcriber-0.1.0-py3-none-any.whl"`,
  adjusting the file name). **Upgrading with `uv tool install --force` and no extra
  removes it**, so repeat the full command after each upgrade.
  ([Linux](install/linux.md#local-faster-whisper-the-asr-local-extra))
- **It is slow**: without an NVIDIA GPU, V transcribes on the CPU. It works, but an
  hour of audio can take a long time; the `turbo` model is the fastest with good
  quality. `voz doctor` shows `GPU/CUDA: solo CPU` when no CUDA was found.
- **CUDA does not load on Windows**: V falls back to the CPU (int8) with a warning;
  the job does not fail. You need the NVIDIA driver, not the CUDA Toolkit.
  macOS always uses the CPU. ([Windows and macOS](install/windows-macos.md#gpu))

## Models

Downloads only happen after you choose and confirm a model; the download details
are in [Model store](models.md).

- **The download was interrupted** (`model_installation_network_error`): the
  partial file is kept; start the download again and it resumes where it stopped.
- **`model_installation_checksum_mismatch`**: a downloaded file did not match its
  expected size or SHA-256 and was deleted; download again. If it keeps failing,
  report it with the diagnostics bundle.
- **`model_installation_http_error`**: the server answered with an error status
  (carried in `error.status`).
- **`disk_space_insufficient`**: there is not enough free space for the pending
  bytes plus a margin. Free space in the data directory (`voz doctor` warns below
  5 GiB free in `data` or `cache`) or remove a model you do not use from the model
  manager.
- **A model shows as not installed although you downloaded it**: if the manifest
  lists a file that is missing, replaced by a symbolic link or of a different
  size, the model is considered not installed and the next download or import
  replaces it.
- **Reusing a model from Buzz**: only snapshots whose source and 40-character
  revision match V's catalog exactly, with every file present, are offered;
  `BUZZ_MODEL_ROOT` selects a non-standard location and `BUZZ_MODEL_ROOT=` (empty)
  disables detection. ([Buzz cache](buzz.md))

## Data and upgrades

- **A database migration failed to start** (`migration_backup_failed`): V makes a
  backup before migrating and does not migrate if the backup fails; the database
  stays intact. Check free space and permissions of `$XDG_STATE_HOME/voz/backups/`.
- **Restoring a backup**: stop V and copy the backup over
  `$XDG_DATA_HOME/voz/voz.sqlite3` (delete `voz.sqlite3-wal` and `-shm` first).
  ([Diagnostics](diagnostics.md#backup-before-migrating))
- **Testing without touching your data on Linux**: export the four `XDG_*_HOME`
  variables to a temporary directory. `uv` honors `XDG_CACHE_HOME` and
  `XDG_DATA_HOME` too, so it will download its package cache and a managed CPython
  again; also export `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` pointing to their
  real locations to avoid that. ([Linux](install/linux.md#where-v-stores-its-data))
- **Uninstalling does not delete your projects or models**; remove the data
  directories yourself if you want them gone.
