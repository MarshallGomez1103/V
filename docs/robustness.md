# Robustez de escrituras críticas (S14.02)

Auditoría del 2026-09-30 de cada escritura cuyo fallo a medias dejaría a VOZ en
un estado ilegible o engañoso: checkpoints de transcripción, metadatos en SQLite,
manifests de modelos, caché de picos y originales/derivados de audio.
Los números de línea son los del commit auditado más los cambios de esta
oleada; si dudas, busca el símbolo.

## Reglas que cumple cada escritura

1. **SQLite**: cada operación es una transacción (`engine.begin()`), con
   `journal_mode=WAL`, `synchronous=FULL` y `foreign_keys=ON` en cada conexión
   (`database.py:47-52`). Una confirmación (`COMMIT`) es durable ante pérdida de
   energía; un proceso muerto antes del `COMMIT` no deja rastro.
2. **Archivos que se sustituyen**: se escriben en un temporal del mismo
   directorio, se hace `fsync` del fichero y después `os.replace`/`os.rename`
   atómico. Un lector nunca ve el contenido a medias.
3. **Archivos inmutables** (originales y derivados): temporal `O_EXCL` 0600,
   `fsync`, publicación con `os.link` (no reemplaza), `fsync` del directorio y
   borrado del temporal. Sin sobrescritura posible.
4. **Directorios de modelos**: se construyen completos en un directorio de
   staging, con manifest como último fichero y `fsync` de todo el árbol, y se
   publican con un único `rename` de directorio.

## Inventario

| # | Escritura crítica | Dónde | Mecanismo | Prueba |
| --- | --- | --- | --- | --- |
| 1 | Checkpoint de chunk + progreso del job | `persistence/transcription_checkpoints.py:184-201` (`commit`) | una transacción: `INSERT` checkpoint + `UPDATE` job | `test_recoverable_transcription.py::test_failed_checkpoint_insert_cannot_advance_job_progress`; **nuevo** `test_atomic_writes.py::test_failure_after_the_checkpoint_insert_rolls_the_insert_back` |
| 2 | Durabilidad del `COMMIT` | `persistence/database.py:47-52` | `synchronous=FULL` explícito (**nuevo**: antes dependía del valor por defecto de la compilación de SQLite) | **nuevo** `test_atomic_writes.py::test_every_connection_syncs_the_wal_on_commit` |
| 3 | Proceso muerto a mitad de transacción | todos los repositories | WAL recupera al último `COMMIT` | **nuevo** `test_atomic_writes.py::test_a_killed_process_mid_transaction_leaves_the_previous_state` (subproceso con `os._exit`) |
| 4 | Guardar segmento + palabras | `persistence/repositories.py:479` (`SqliteSegmentRepository.save`) | `UPDATE` + `DELETE` palabras + `INSERT` palabras en una transacción | **nuevo** `test_failed_segment_save_rolls_back_text_and_words` |
| 5 | Reemplazar turnos de hablante | `repositories.py:695` (`replace_for_transcript`) | `DELETE` + `INSERT` en una transacción | **nuevo** `test_failed_turn_replacement_keeps_the_previous_turns` |
| 6 | Asignar hablantes en lote | `repositories.py:514` (`update_speakers`) | un `UPDATE` por segmento dentro de una transacción; FK rechaza hablantes inexistentes | **nuevo** `test_failed_speaker_batch_changes_no_segment` |
| 7 | Edición de texto con revisión | `repositories.py:497` (`update_text_if_revision`) | `UPDATE ... WHERE revision = ?` (compare-and-set) | `test_sqlite_segment_editing.py::test_update_text_if_revision_is_conditional` |
| 8 | Transcript final del job | `application/job_runner.py` `_persist_transcript` | identidades `uuid5` deterministas; cada segmento es su transacción y la reanudación añade solo los que faltan; el job pasa a `COMPLETED` después | `test_job_runner.py` (`_CrashingTranscripts`, `_CrashingSegments`, `_CrashingJobs`, parametrizado por segmento) |
| 9 | Backup antes de migrar | `persistence/migrate.py:83-116` | API de backup de SQLite → `.partial` → `fsync` → `os.replace` → `fsync` del directorio; si falla, no se migra | `test_migration_backup.py` |
| 10 | Importar original | `infrastructure/media_storage.py:40` (`import_original`) y `_publish_without_replacement` (`:500`) | temporal `O_EXCL`, `fsync`, `os.link`, `fsync` de directorio, rollback confirmado | `test_media_storage.py::test_publish_fsync_failure_rolls_back_destination`, `::test_publish_reports_when_rollback_cannot_be_confirmed`, `::test_import_fsyncs_directory_after_publish_and_temporary_unlink`, `::test_temporary_is_made_read_only_before_file_fsync` |
| 11 | Fila `media_assets` tras publicar el original | `application/import_media.py:112` | si el `INSERT` falla se descarta el original (compensación); si el resultado es incierto se conserva | `test_import_media.py::test_repository_failure_discards_published_original_and_reraises`, `test_import_media_sqlite.py::test_sqlite_rejection_compensates_the_published_original` |
| 12 | Derivado normalizado (WAV 16 kHz) | `infrastructure/audio/ffmpeg.py:480` (`_publish_without_replacement`), `fsync` en `:457` | igual que el 10 | `test_ffmpeg_media_normalizer_integration.py::test_temporary_fsync_failure_is_io_error_and_does_not_publish`, `::test_publication_fsync_failure_rolls_back_and_is_reported` |
| 13 | Manifest de modelo Faster Whisper (descarga) | `infrastructure/model_storage.py:654` (`_commit`) y `:840` (`_write_manifest`) | manifest con `open("x")` + `fsync` en el staging, `_sync_tree`, `os.rename(staging, final)` (`:688`) | `test_model_download.py::test_published_directory_with_wrong_size_is_not_installed_and_replaced`; **nuevo** `test_atomic_file_writes.py::test_model_install_that_fails_before_publication_leaves_nothing` (rename y fsync inyectados) y `::test_published_model_is_never_touched_by_a_later_failing_install` |
| 14 | Fichero de modelo descargado | `model_storage.py:532` (`os.replace(partial, finished)`) y `:625` | `.part` reanudable + `fsync` + verificación de tamaño/SHA-256 + `os.replace` | `test_model_download.py` (reanudación, checksum, conexión cortada) |
| 15 | Importar snapshot local/Buzz | `model_storage.py:303` (`import_local_snapshot`) | hardlink/copia a `.import-*.tmp`, mismo `_commit` que el 13; nunca modifica el origen | `test_model_download.py::test_import_*`, `test_buzz_import.py` |
| 16 | Borrado de un modelo | `model_storage.py:700` (`_discard`) | `rename` a `.remove-*.tmp` y luego `rmtree`: nunca queda un directorio canónico medio borrado | `test_model_download.py::test_remove_can_delete_a_directory_whose_files_were_damaged` |
| 17 | Modelos de diarización | `infrastructure/diarization/models.py:194` (`_publish`) y `:206` (`os.rename`) | staging estable y reanudable; **nuevo**: `fsync` del modelo extraído (`:230`) y del manifest (`:203`), que es el marcador de commit; `paths()` exige manifest y tamaños exactos | **nuevo** `test_atomic_file_writes.py::test_diarization_publish_failure_leaves_no_half_installed_directory`, `::test_diarization_files_and_manifest_are_synced_before_the_rename`, `::test_diarization_interrupted_before_the_manifest_is_not_installed`; `test_diarization_models.py::test_truncated_install_is_detected_and_repaired` |
| 18 | Caché de picos de waveform | `infrastructure/audio/waveform_peaks.py:270-283` (`_write_cache`) | temporal + **nuevo** `fsync` + `os.replace`; ante `OSError` se borra el temporal; el lector valida y descarta JSON corrupto | **nuevo** `test_atomic_file_writes.py::test_peaks_cache_write_syncs_the_file_before_the_rename`, `::test_failed_peaks_cache_write_keeps_the_previous_entry_and_no_temp_file`; `test_ffmpeg_waveform_peaks_integration.py::test_corrupt_cache_is_ignored_and_rewritten` |

## Cambios de código de esta auditoría

- `database.py`: `PRAGMA synchronous=FULL` explícito por conexión.
- `waveform_peaks.py`: `fsync` del temporal antes de `os.replace`.
- `diarization/models.py`: `fsync` del manifest y del modelo extraído antes de
  publicar el directorio.

## Hallazgos que quedan abiertos

- **Job y selección no son atómicos** (`application/create_transcription_job.py`,
  `self.jobs.add(job)` seguido de `self.selections.add(selection)`: dos
  transacciones). Una muerte entre ambas deja un job `QUEUED` sin selección; al
  reiniciar, `runner.recover()` lo reencola y `JobRunner` lo termina en `FAILED`
  con `job_selection_missing` (no hay corrupción ni bucle, pero el usuario ve un
  job fallido que nunca pudo empezar). Arreglo propuesto (fuera de esta
  oleada, el archivo lo toca otro agente): una sola transacción en un
  repository que añada job y selección, o compensar con borrado del job si
  `selections.add` falla.
- **Originales huérfanos**: si el proceso muere entre la publicación del original
  y el `INSERT` de `media_assets`, queda un `*.original` sin fila. No corrompe
  nada, solo ocupa disco. Hace falta un barrido de huérfanos (no existe).
- **Migraciones no transaccionales en SQLite**: Alembic no puede deshacer DDL de
  SQLite de forma fiable; la garantía es el backup previo (#9), no un rollback.
- **Reintento tras un fallo de publicación de diarización** vuelve a descargar el
  archivo de segmentación (se borra antes de publicar); el embedding y los
  ficheros extraídos se reutilizan. Es ineficiencia, no pérdida de datos.
- `rename` de directorios de modelo no hace `fsync` del directorio padre en el
  instalador de diarización; si la energía falla justo después, `paths()` ve un
  directorio ausente o con tamaños erróneos y reinstala.

## Cierre y reapertura durante un job largo (S14.13)

`tests/e2e/test_restart_during_job.py` cierra la app HTTP (salida del lifespan)
con un provider lento de 8 chunks detenido en la llamada 3, reabre con los mismos
directorios XDG y comprueba: el job queda `TRANSCRIBING` con 3 checkpoints y 3/8
de progreso sin transcript; al reabrir termina `COMPLETED`; los chunks 0-2 no se
repiten (audio distinto por chunk, conjuntos disjuntos), hay exactamente 8
segmentos en orden y una tercera apertura no vuelve a ejecutar ASR.
