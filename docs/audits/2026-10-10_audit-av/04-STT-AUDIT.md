# 04 · Auditoría del flujo STT

Flujo pedido: archivo → FFmpeg → normalización → chunks → ASR → timestamps → diarización → persistencia → UI → exportación.

## Mapa real del flujo

| Etapa | Qué ocurre | Código | Estado |
|---|---|---|---|
| 1. Subida | Stream a disco con límite de tamaño, SHA-256 durante la copia, original inmutable | `interfaces/api/media.py:36,170-206`; `infrastructure/media_storage.py`; `application/import_media.py` | Implementada y probada |
| 2. Sondeo | `ffprobe` con timeout; rechaza códecs no utilizables y duraciones extremas | `infrastructure/audio/ffprobe.py` (fuzz en `test_ffprobe_fuzz.py`) | Implementada y probada |
| 3. Normalización | FFmpeg a PCM 16 kHz mono; progreso monotónico; validación de WAV; publicación sin reemplazo | `infrastructure/audio/ffmpeg.py:64-160,420-530`; `application/normalize_media.py` | Implementada; probada con FFmpeg real en tests de integración |
| 4. Planificación de chunks | 30 min con solape de 5 s; cada chunk "posee" sus segmentos | `application/job_runner.py:76-77`; `application/chunked_transcription.py:83` (`plan_audio_chunks`) | Implementada y probada |
| 5. ASR | faster-whisper (local), whisper.cpp (CLI), OpenAI y ElevenLabs (cloud, fakes) | `infrastructure/asr/*.py`, `infrastructure/cloud/*.py` | Ver tabla de providers |
| 6. Checkpoints | Un checkpoint por chunk en SQLite, con plan/modelo/source/revisión/idioma | `application/recoverable_transcription.py`; `persistence/transcription_checkpoints.py`; migración 0002 | Implementada y probada (ASR-RECOVERY-001) |
| 7. Timestamps | Segmentos con offsets globales; palabras nativas de faster-whisper (`word_timestamps`) | `infrastructure/asr/faster_whisper.py:529` (`_canonical_word`); `application/chunked_transcription.py:143` (`globalize_chunk_result`) | Implementada; WhisperX descartado (ADR-0008) |
| 8. Diarización | sherpa-onnx en subproceso; reconciliación por solape máximo; etapa `DIARIZING` opcional | `infrastructure/diarization/sherpa.py:50` (umbral 0.4); `worker.py`; `application/diarization_reconcile.py` | Implementada; fallo de diarización no pierde el transcript |
| 9. Persistencia | Transcript, segmentos, palabras, hablantes, turnos en SQLite con WAL y `synchronous=FULL` | `persistence/*.py`; migraciones 0001–0008 | Implementada y probada |
| 10. UI | Progreso por SSE; editor con autosave; forma de onda; revisión | `apps/web/src/components/*` | Ver `05-UI-UX-AUDIT.md` |
| 11. Exportación | TXT, Markdown, SRT, VTT, JSON canónico `voz.transcript` v1 | `application/export/*.py`; `interfaces/api/export.py` | Implementada; goldens |

## Providers

| Provider | Tipo | Estado verificado | Límite |
|---|---|---|---|
| faster-whisper (`turbo`, `large-v3`, `medium`, `small`, `base`) | Local | Verificado en RTX 4060 según ROADMAP (BENCH-002: turbo RTF 0,025, WER 1,66 %; large-v3 RTF 0,073, WER 1,99 %) | CUDA declarado experimental en README |
| whisper.cpp v1.9.4 | Local (CLI externo, `VOZ_WHISPER_CPP_BIN` o `whisper-cli` en PATH) | CPU verificada: RTF 0,80, WER 1,83 % (ROADMAP WCPP-004) | CUDA y Vulkan no verificados (HANDOFF) |
| OpenAI (`whisper-1`, `gpt-4o-transcribe-diarize`) | Cloud | Solo transporte falso | Nunca probado contra el servicio |
| ElevenLabs Scribe v1 | Cloud | Solo transporte falso | Nunca probado contra el servicio |
| Fake de whisper.cpp | Test | `tests/fixtures/whisper_cpp/fake_whisper_cli.py` | Solo tests |

Medidas de benchmark: en el repositorio, `docs/benchmarks.md` y ROADMAP BENCH-002 usan audio **sintético**. Los datos privados del responsable no están en el repo y no se usaron en esta auditoría.

## Descarga de modelos

- Catálogo con revisión fijada y SHA-256 por archivo (`infrastructure/asr/catalog.py`, `whisper_cpp_catalog.py`). Las revisiones son hashes de 40 caracteres.
- Descarga con reanudación `Range`, `.part` descartado si está corrupto, verificación de tamaño y SHA-256 (`infrastructure/model_storage.py`, `test_model_download.py`).
- No se descargó ningún modelo en esta auditoría.
- Importación desde caché de Buzz por hardlink, de solo lectura (`infrastructure/buzz_cache.py`, ROADMAP MODELS-BUZZ-001).
- Riesgo residual: `faster_whisper_fast_descriptor(revision=None)` (`catalog.py:26`) permite construir un descriptor sin revisión. Hoy los callers pasan revisión; el default existe y es una trampa potencial.

## Selección CPU/GPU y VRAM

- Detección sin shell: `nvidia-smi` y meminfo (`infrastructure/asr/system_resources.py`, `hardware.py`).
- Recomendación por hardware (`application/hardware_recommendation.py:26-55`): CUDA con VRAM ≥ 6 GiB → `turbo`; 5–6 GiB → `medium`; < 5 GiB → `small`; CPU con RAM ≥ 8 GiB → `small`; si no, `base`.
- Bloqueo antes de crear el job: `409 insufficient_vram` / `insufficient_ram` (ROADMAP HW-RECOMMEND-001).
- Gestión de VRAM entre etapas: el ASR se libera antes de diarizar (`release_asr`, `job_runner.py:213`, S6.15/S14.07).
- Fallback GPU → CPU con causa observable (`_cpu_fallback_notice`, `faster_whisper.py:163`).
- CUDA: precarga de bibliotecas nvidia desde wheels (`faster_whisper.py:94-160`). Verificada en el equipo del propietario según ROADMAP; no re-verificada aquí.

## Concurrencia y cancelación

- Concurrencia de jobs = 1 (un worker). Deliberado (ver `03-ARCHITECTURE-AUDIT.md`).
- Cancelación: `JobRunner.cancel` pasa a `CANCELLING` y el worker termina en `CANCELLED` entre unidades. Dentro del ASR, `_raise_if_cancelled` se consulta antes y después de cada llamada al motor y entre segmentos (`faster_whisper.py:329,336,353,375,431,434`).
- Granularidad real: una llamada `transcribe` de faster-whisper sobre un chunk de 30 min **no se interrumpe a mitad**; la cancelación actúa entre segmentos que emite el generador. Documentado como límite, no como bug.
- whisper.cpp: el proceso se mata (`whisper_cpp.py:300-304`) y la cancelación es efectiva.
- Cancelación de FFmpeg: `_stop_process` (`ffmpeg.py:359`) con cierre de pipes.

## Recuperación

- Al arranque, `JobRunner.recover()` reencola todos los jobs no terminales (`job_runner.py:254`). Los checkpoints hacen la reanudación idempotente.
- Test de reinicio durante un job: `tests/e2e/test_restart_during_job.py` (pasó en la suite).
- Backup de SQLite antes de migrar, con retención de 5 y aborto si falla (ROADMAP DIAG-001).
- Fallo de persistencia en el worker: **silencioso** (AV-P1-03). Si `_save` falla dentro de `_loop`, el job puede quedar en un estado no terminal sin que nadie lo vea hasta el siguiente arranque.

## Timestamps, speakers, edición, exportación

- Timestamps: offsets globales sin solapes entre chunks; `owned_chunk_segments` evita duplicados en el solape (verificado en tests de chunking).
- Speakers: paleta persistente; reconciliación por solape máximo; `AssignSpeakers` idempotente y conserva renombres (DIAR-CORE-001/002).
- Recalcular hablantes (`rediarize`): solo recalcula hablantes sin re-transcribir (`application/rediarize.py`, 457 líneas de test). No se probó en navegador en esta auditoría.
- Edición: PUT con revisión optimista (UPDATE condicional) y 409 resoluble en UI (SEGMENTS-EDIT-001, SEGMENT-EDITOR-001).
- Exportación: 5 formatos, `filename*` RFC 5987, nombres de archivo seguros y anti-traversal (`export/filenames.py`).

## Archivos corruptos y entradas hostiles

- Sondeo con timeout y fuzz de ffprobe (2 bugs corregidos según ROADMAP ROBUST-001).
- Normalización: si FFmpeg falla, se limpia el temporal y se devuelve error tipado (`ffmpeg.py:287`, `import_media.py:92`).
- Validación de WAV antes de publicar (`ffmpeg.py:450-463`).
- Duración extrema (`ffprobe.py:25`): sin excepción cruda.

## Limitaciones y defectos del STT

| ID | Descripción | Severidad | Estado |
|---|---|---|---|
| STT-01 | Fallo silencioso en `JobRunner._loop` | P1 | Verificado por lectura (AV-P1-03) |
| STT-02 | Cancelación no interrumpe a mitad de un `transcribe` por chunk | P3 | Verificado por lectura; límite de la librería |
| STT-03 | Umbral de diarización 0.4 medido en un único audio privado | P2 | Consta en el plan de la versión 3; no reproducible públicamente |
| STT-04 | `large-v3` con WER 8 % en clip largo "sin investigar" | P2 | Consta en HANDOFF |
| STT-05 | Perfil `academic` sin medición de calidad | P3 | Consta en HANDOFF |
| STT-06 | Cloud nunca probado contra servicio real | P2 | Consta en ROADMAP y HANDOFF |
| STT-07 | whisper.cpp CUDA/Vulkan sin verificar | P2 | Consta en HANDOFF |
| STT-08 | Glosario muestra ids crudos en "Lo usan" | P3 | Consta en HANDOFF |

## Qué no se pudo verificar en esta auditoría

- Una transcripción real con modelo descargado (no se descargaron modelos; el test real está marcado opt-in y se omitió).
- Rendimiento en GPU propia (no se ejecutaron benchmarks pesados).
- Diarización con el audio de referencia del propietario (opt-in `VOZ_DIARIZATION_E2E_*`, omitido).
