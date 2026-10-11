# Robustness of critical writes (S14.02)

Audit of 2026-09-30 of every write whose half-finished failure would leave V in
an unreadable or misleading state: transcription checkpoints, SQLite metadata,
model manifests, the peaks cache, and audio originals/derivatives. Line numbers
are those of the audited commit plus the changes of this wave; if in doubt,
search for the symbol.

## Rules every write follows

1. **SQLite**: every operation is a transaction (`engine.begin()`), with
   `journal_mode=WAL`, `synchronous=FULL` and `foreign_keys=ON` on every
   connection (`database.py:47-52`). A `COMMIT` is durable against power loss; a
   process killed before the `COMMIT` leaves no trace.
2. **Files that get replaced**: written to a temporary file in the same
   directory, `fsync` of the file, then an atomic `os.replace`/`os.rename`. A
   reader never sees half-written content.
3. **Immutable files** (originals and derivatives): `O_EXCL` 0600 temporary file,
   `fsync`, publication with `os.link` (does not replace), directory `fsync` and
   removal of the temporary file. Overwriting is impossible.
4. **Model directories**: built completely in a staging directory, with the
   manifest as the last file and an `fsync` of the whole tree, and published with
   a single directory `rename`.

## Inventory

| # | Critical write | Where | Mechanism | Test |
| --- | --- | --- | --- | --- |
| 1 | Chunk checkpoint + job progress | `persistence/transcription_checkpoints.py:184-201` (`commit`) | one transaction: `INSERT` checkpoint + `UPDATE` job | `test_recoverable_transcription.py::test_failed_checkpoint_insert_cannot_advance_job_progress`; **new** `test_atomic_writes.py::test_failure_after_the_checkpoint_insert_rolls_the_insert_back` |
| 2 | `COMMIT` durability | `persistence/database.py:47-52` | explicit `synchronous=FULL` (**new**: it used to depend on the default of the SQLite build) | **new** `test_atomic_writes.py::test_every_connection_syncs_the_wal_on_commit` |
| 3 | Process killed mid-transaction | all repositories | WAL recovers to the last `COMMIT` | **new** `test_atomic_writes.py::test_a_killed_process_mid_transaction_leaves_the_previous_state` (subprocess with `os._exit`) |
| 4 | Save segment + words | `persistence/repositories.py:479` (`SqliteSegmentRepository.save`) | `UPDATE` + `DELETE` words + `INSERT` words in one transaction | **new** `test_failed_segment_save_rolls_back_text_and_words` |
| 5 | Replace speaker turns | `repositories.py:695` (`replace_for_transcript`) | `DELETE` + `INSERT` in one transaction | **new** `test_failed_turn_replacement_keeps_the_previous_turns` |
| 6 | Batch speaker assignment | `repositories.py:514` (`update_speakers`) | one `UPDATE` per segment inside a transaction; the FK rejects nonexistent speakers | **new** `test_failed_speaker_batch_changes_no_segment` |
| 7 | Text edit with revision | `repositories.py:497` (`update_text_if_revision`) | `UPDATE ... WHERE revision = ?` (compare-and-set) | `test_sqlite_segment_editing.py::test_update_text_if_revision_is_conditional` |
| 8 | The job's final transcript | `application/job_runner.py` `_persist_transcript` | deterministic `uuid5` identities; each segment is its own transaction and resuming adds only the missing ones; the job moves to `COMPLETED` afterwards | `test_job_runner.py` (`_CrashingTranscripts`, `_CrashingSegments`, `_CrashingJobs`, parametrized per segment) |
| 9 | Backup before migrating | `persistence/migrate.py:83-116` | SQLite backup API → `.partial` → `fsync` → `os.replace` → directory `fsync`; if it fails, no migration runs | `test_migration_backup.py` |
| 10 | Import an original | `infrastructure/media_storage.py:40` (`import_original`) and `_publish_without_replacement` (`:500`) | `O_EXCL` temporary file, `fsync`, `os.link`, directory `fsync`, confirmed rollback | `test_media_storage.py::test_publish_fsync_failure_rolls_back_destination`, `::test_publish_reports_when_rollback_cannot_be_confirmed`, `::test_import_fsyncs_directory_after_publish_and_temporary_unlink`, `::test_temporary_is_made_read_only_before_file_fsync` |
| 11 | `media_assets` row after publishing the original | `application/import_media.py:112` | if the `INSERT` fails the original is discarded (compensation); if the outcome is uncertain it is kept | `test_import_media.py::test_repository_failure_discards_published_original_and_reraises`, `test_import_media_sqlite.py::test_sqlite_rejection_compensates_the_published_original` |
| 12 | Normalized derivative (16 kHz WAV) | `infrastructure/audio/ffmpeg.py:480` (`_publish_without_replacement`), `fsync` at `:457` | same as 10 | `test_ffmpeg_media_normalizer_integration.py::test_temporary_fsync_failure_is_io_error_and_does_not_publish`, `::test_publication_fsync_failure_rolls_back_and_is_reported` |
| 13 | Faster Whisper model manifest (download) | `infrastructure/model_storage.py:654` (`_commit`) and `:840` (`_write_manifest`) | manifest with `open("x")` + `fsync` in staging, `_sync_tree`, `os.rename(staging, final)` (`:688`) | `test_model_download.py::test_published_directory_with_wrong_size_is_not_installed_and_replaced`; **new** `test_atomic_file_writes.py::test_model_install_that_fails_before_publication_leaves_nothing` (rename and fsync injected) and `::test_published_model_is_never_touched_by_a_later_failing_install` |
| 14 | Downloaded model file | `model_storage.py:532` (`os.replace(partial, finished)`) and `:625` | resumable `.part` + `fsync` + size/SHA-256 verification + `os.replace` | `test_model_download.py` (resume, checksum, dropped connection) |
| 15 | Import a local/Buzz snapshot | `model_storage.py:303` (`import_local_snapshot`) | hardlink/copy to `.import-*.tmp`, same `_commit` as 13; never modifies the source | `test_model_download.py::test_import_*`, `test_buzz_import.py` |
| 16 | Deleting a model | `model_storage.py:700` (`_discard`) | `rename` to `.remove-*.tmp` and then `rmtree`: a half-deleted canonical directory never remains | `test_model_download.py::test_remove_can_delete_a_directory_whose_files_were_damaged` |
| 17 | Diarization models | `infrastructure/diarization/models.py:194` (`_publish`) and `:206` (`os.rename`) | stable, resumable staging; **new**: `fsync` of the extracted model (`:230`) and of the manifest (`:203`), which is the commit marker; `paths()` requires the manifest and exact sizes | **new** `test_atomic_file_writes.py::test_diarization_publish_failure_leaves_no_half_installed_directory`, `::test_diarization_files_and_manifest_are_synced_before_the_rename`, `::test_diarization_interrupted_before_the_manifest_is_not_installed`; `test_diarization_models.py::test_truncated_install_is_detected_and_repaired` |
| 18 | Waveform peaks cache | `infrastructure/audio/waveform_peaks.py:270-283` (`_write_cache`) | temporary file + **new** `fsync` + `os.replace`; on `OSError` the temporary file is removed; the reader validates and discards corrupt JSON | **new** `test_atomic_file_writes.py::test_peaks_cache_write_syncs_the_file_before_the_rename`, `::test_failed_peaks_cache_write_keeps_the_previous_entry_and_no_temp_file`; `test_ffmpeg_waveform_peaks_integration.py::test_corrupt_cache_is_ignored_and_rewritten` |

## Code changes from this audit

- `database.py`: explicit `PRAGMA synchronous=FULL` per connection.
- `waveform_peaks.py`: `fsync` of the temporary file before `os.replace`.
- `diarization/models.py`: `fsync` of the manifest and of the extracted model
  before publishing the directory.

## Resolved since the audit

- **Job and selection were not atomic.** The audit found that
  `application/create_transcription_job.py` called `self.jobs.add(job)` and then
  `self.selections.add(selection)` as two transactions, so a death between them
  left a `QUEUED` job without a selection (on restart `runner.recover()` would
  re-enqueue it and `JobRunner` would end it as `FAILED` with
  `job_selection_missing`). `CreateTranscriptionJob` now takes a `job_writer`
  (port `JobWithSelectionWriter`, `add_with_selection`) that adds both rows in one
  transaction; `bootstrap.py` wires it, and the two-call path remains only as a
  fallback when no writer is injected.

## Findings that remain open

- **Orphaned originals**: if the process dies between publishing the original and
  the `INSERT` into `media_assets`, a `*.original` file is left without a row. It
  corrupts nothing, it only takes up disk. An orphan sweep is needed (none
  exists).
- **Non-transactional migrations in SQLite**: Alembic cannot reliably undo SQLite
  DDL; the guarantee is the prior backup (#9), not a rollback.
- **Retrying after a diarization publication failure** downloads the segmentation
  archive again (it is deleted before publishing); the embedding and the extracted
  files are reused. This is inefficiency, not data loss.
- Model directory `rename` does not `fsync` the parent directory in the
  diarization installer; if power fails right after, `paths()` sees a missing
  directory or wrong sizes and reinstalls.

## Shutdown and reopening during a long job (S14.13)

`tests/e2e/test_restart_during_job.py` closes the HTTP app (lifespan exit) with a
slow 8-chunk provider stopped at call 3, reopens with the same XDG directories
and checks: the job is left `TRANSCRIBING` with 3 checkpoints and 3/8 progress
and no transcript; on reopening it ends `COMPLETED`; chunks 0–2 are not repeated
(distinct audio per chunk, disjoint sets), there are exactly 8 segments in order,
and a third opening does not run ASR again.
