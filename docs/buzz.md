# Reusing models from the Buzz cache

If you already use [Buzz](https://github.com/chidiwilliams/buzz), V (formerly
VOZ) can adopt some of its models so you do not download them twice. Buzz is
**not** a dependency of V: only its cache is read, and only when you ask for an
import.

## What is detected

Faster-whisper format in the HuggingFace hub layout:

```text
<root>/models--<org>--<repo>/snapshots/<revision>/{model.bin,config.json,...}
```

(the snapshot files are symlinks to `../../blobs/<hash>`). Roots searched, in
this order (the first one that has the model wins):

1. `$BUZZ_MODEL_ROOT`, if defined and non-empty.
2. `~/.var/app/io.github.chidiwilliams.Buzz/cache/Buzz/models` (Flatpak).
3. `${XDG_CACHE_HOME:-~/.cache}/Buzz/models`.

A model is a candidate only if ALL of the following hold:

- `source` and `revision` (a 40-character commit SHA) match an entry of V's
  catalog (`faster_whisper_catalog()`) **exactly**; a different revision is
  ignored even if it is "the same" model.
- All the catalog's files exist with the expected size.
- Each symlink, once resolved, stays inside that repository's HF directory
  (those pointing outside it, or to another repository, are rejected) and is a
  regular file.

Ignored: `whisper/*.pt` (openai-whisper format, incompatible), models from other
revisions, incomplete snapshots, unreadable or nonexistent roots (no error).
`.buzz_complete` is not required.

## What is not touched

Detection only uses `os.stat` and `os.path.realpath`: it opens no files, creates
no directories and writes nothing. The import
(`FileSystemModelStore.import_local_snapshot`) only reads the source: it
hard-links (or copies, if it is a different filesystem) into a staging directory
owned by V, verifies size and SHA-256, and publishes atomically with its
manifest. Buzz keeps working as before; nothing in its cache is ever moved or
deleted. A hard link adds one more name to the same inode (it changes its link
count and ctime, not its content or mtime). Deleting the model from V only
removes V's own link.

## How to disable it

`BUZZ_MODEL_ROOT=` (defined but **empty**) turns Buzz detection off entirely. To
point to a non-standard location, use `BUZZ_MODEL_ROOT=/path/to/models`.

## Internal contract

- Port `voz.application.ports.external_models`: `ExternalModelCandidate`,
  `ExternalModelSource.find_candidates()`, `ExternalModelError`.
- Adapter `voz.infrastructure.buzz_cache.BuzzModelCache`.
- Use case `voz.application.import_external_model.ImportExternalModel`:
  `available(origin="buzz")` and `execute(model_id, origin="buzz", progress=,
  cancelled=)`. Stable errors: `external_model_unknown_model`,
  `external_model_not_found`, plus the `model_installation_*` codes of the store.
- Host paths (`snapshot_dir`) must never reach the browser.

See also [Model store](models.md) for how the import is carried out.
