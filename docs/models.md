# Model store: download, import and removal

Behavior of the `FileSystemModelStore` adapter
(`src/voz/infrastructure/model_storage.py`) for Section 8 (S8.04-S8.06, S8.15)
and Section 14 (S14.04, S14.09). Application contract: `ModelFile` and
`ModelDownloadPort` in `application/ports/model_installation.py`. The underlying
decision (pinned revision, manifest, explicit installation) remains in
[ADR-0004](adr/0004-local-asr-and-recoverable-chunks.md). None of this runs
unless the caller asks for it: importing V downloads nothing.

The model directory lives under the data directory (`~/.local/share/voz/models/`
on Linux; the `voz` name does not change, see
[ADR-0009](adr/0009-rename-to-v.md)). For installation and platform paths see
[Linux](install/linux.md) and [Windows and macOS](install/windows-macos.md); for
common failures see [Troubleshooting](troubleshooting.md).

## Add and manage a local model

Open **Models → Add model**, paste a direct download link or a public Hugging
Face repository, and choose **Check link**. Review the detected format, download
size and license before confirming. Manual configuration also accepts compatible
browser-selected folders and explicit file roles.

Checking a remote link contacts its host for metadata; confirming installation
downloads the weights. Direct links must use HTTP(S), without embedded
credentials, query strings or fragments, and provide a usable file size. Use
trusted sources: URL handling follows redirects and does not restrict destinations
to public networks.

A link supplies model files, not a new engine: the weights must match an
installed engine and supported family. See the [import formats and limits](api/models.md#custom-model-imports).
The model manager shows installation state, download size, installed file size
and free space. Deletion requires confirmation and reports reclaimable space
when known; files shared with another cache may remain on disk. The storage
location follows the platform data directory described above; the browser does
not expose absolute host paths. Original import folders remain untouched.

## Input: `ModelFile`

Each file of the snapshot is declared with `name` (a basename, without `/`, `\`,
`..`, not `.voz-model.json` and without the `.part` suffix), `size_bytes > 0` and
`sha256` (64 lowercase hex characters, or `None` when upstream does not publish
it, e.g. non-LFS files). The descriptor must have a `source` and a 40-hex
revision; without them the error is `model_installation_provenance_required`.

## `download(descriptor, files, *, base_url, progress, cancelled)`

- URL: `{base_url}/{source}/resolve/{revision}/{name}`; `http`/`https` only.
- Deterministic staging in `models/<provider>/.download-<hash>/` with
  `name.part`. A complete, verified file is renamed to `name` inside the staging
  directory.
- `progress(done, total)`: accumulated bytes of all files (those already on disk
  count from the first call); `total = sum(size_bytes)`.
- `cancelled()` is polled between 1 MiB blocks (and while the SHA-256 is being
  computed). Cancelling leaves the `.part` intact and raises
  `model_installation_cancelled`.
- Per-file verification: exact size and SHA-256 if present. A mismatch deletes
  that file and raises `model_installation_checksum_mismatch`.
- Publication: manifest `.voz-model.json` (now with a `files` list holding name,
  size and sha256), `fsync` and atomic `rename`, reusing the logic of `install`.
  If another installer won the race, its installation is kept.

### Resuming and recovery (S8.15, S14.09)

A second call resumes each `.part` with `Range: bytes=N-`:

| Situation | Result |
| --- | --- |
| Server answers 206 with a consistent `Content-Range` | continues from N |
| Server answers 200 (no Range support) | restarts that file |
| 206 with an inconsistent start, or 416 | discards the `.part` and retries once from scratch |
| `.part` larger than `size_bytes` | discarded and downloaded again |
| File already complete in staging but corrupt | discarded and downloaded again |
| Connection cut midway | `model_installation_network_error`, the `.part` is kept |

A published directory whose manifest lists `files` with any file missing, a
symbolic link, or a different size is considered **not installed**
(`is_installed`, `resolve_path` and `registered_descriptors` exclude it), and the
next `download`/`import_local_snapshot` replaces it. Older manifests (without
`files`, written by `install`) are validated as before.

### Free space check (S14.04)

Before opening the network, `bytes pending + margin` must be free, checked through
`require_free_space` (`DiskSpacePort` is injected in the constructor; without it
the check is skipped). Bytes already present in staging do not count as pending.
The port has no `MODELS` location; `DiskLocation.DERIVATIVES` is used, which lives
under the same data directory. An `ENOSPC` during writing is translated the same
way.

### Errors (`ModelInstallationFailureCode`)

Stable codes, all prefixed `model_installation_` except the disk one:
`model_installation_cancelled`, `model_installation_checksum_mismatch`,
`model_installation_network_error` (timeout, connection, cut),
`model_installation_http_error` (with `error.status`),
`disk_space_insufficient`, `model_installation_not_installed`, plus the existing
ones (`model_installation_confirmation_required`,
`model_installation_provenance_required`, `model_installation_download_failed`,
`model_installation_invalid_snapshot`, `model_installation_io_error`). Messages
include neither paths nor URLs. The per-read network timeout is
`network_timeout_seconds` in the constructor (30 s).

## `import_local_snapshot(descriptor, files, snapshot_dir, *, progress, cancelled)`

Adopts someone else's snapshot (e.g. Buzz's Hugging Face cache:
`snapshots/<rev>/x -> ../../blobs/<hash>`; see [Buzz cache](buzz.md)) **without
ever writing inside `snapshot_dir`**. It resolves the links, checks existence and
size of all files before creating anything, and for each file tries `os.link`
(same filesystem: no duplicated space) and, if that fails, `shutil.copyfile`
(checking space before copying). It verifies SHA-256 when one exists; progress
counts verified bytes (the full size if there is no digest). Cancelling or failing
removes the staging directory (`.import-*.tmp`); there is no resume because
linking is cheap.

## `remove` and `disk_usage`

`remove(descriptor) -> int` renames the descriptor's canonical V directory to
`.remove-*.tmp` and deletes it; it never touches other models or the source
cache. Files with more than one hard link (adopted from another cache) do not
free space and are not counted in the returned value. It raises
`model_installation_not_installed` if there is no matching manifest (a damaged
directory can still be deleted). `disk_usage(descriptor)` sums the on-disk sizes
or returns `None`.

## Known limits

- There is no lock between two simultaneous `download` calls for the same model;
  the jobs layer must serialize them (the SHA-256 protects the integrity of LFS
  files).
- A complete file in staging is hashed again when resuming.
