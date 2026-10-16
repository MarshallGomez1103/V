# VOZ roadmap

Este archivo es la fuente pública de verdad sobre el avance del producto. El
plan de fondo y sus razones están en [VOZ_PLAN_MAESTRO.md](VOZ_PLAN_MAESTRO.md).
El estado privado y transitorio de una sesión pertenece en `.ai/HANDOFF.md`.

## Convenciones

- Cada logro tiene un ID estable `S<section>.<number>`. Un ID publicado nunca se
  renumera ni se reutiliza; los nuevos logros se agregan al final de su sección.
- `[ ]` significa pendiente, `[x]` significa verificado. Código escrito pero no
  comprobado continúa pendiente.
- Una asignación comprende de uno a tres IDs estrechamente relacionados. Una
  excepción de bootstrap debe quedar explícita en el tablero.
- Estados permitidos: `pendiente`, `en curso`, `bloqueado`, `verificado`.
- La columna **Último logro verificable** describe el último checkpoint pequeño
  que sobrevivirá aunque una sesión termine. No describe intenciones vagas.
- La arquitectura duradera se registra en ADRs; el tablero no sustituye los ADR.

## Regla de actualización atómica

Antes de editar, el agente añade o reclama una fila con IDs exactos y estado `en
curso`. Nadie trabaja simultáneamente los mismos IDs. Después de cada checkpoint
verificado, se deben cambiar **en la misma edición**: el checkbox correspondiente,
el estado de la asignación y el último logro verificable. Si las pruebas fallan o
no pueden ejecutarse, el checkbox queda abierto y la fila registra el fallo o
bloqueo. No se marcan rangos completos por inferencia ni se borran logros de
otros agentes. El coordinador libera o reasigna IDs abandonados de forma
explícita.

## Trabajo activo inicial

| Paquete | IDs | Agente | Estado | Último logro verificable |
| --- | --- | --- | --- | --- |
| BOOT-INT-001 | S1.01, S1.02 | `root` | verificado | Repositorio `main` inicializado y licencia MIT presente. |
| BOOT-INT-002 | S1.16, S1.19 | `root` | verificado | CI reproduce los checks locales; `.ai/`, secretos, medios, modelos y artefactos están excluidos. |
| BOOT-BE-001 | S1.03, S1.10, S1.11 | `backend_cli` | verificado | `uv sync --locked`, Ruff y Pyright pasaron con el entorno declarado. |
| BOOT-BE-002 | S1.05, S1.12 | `backend_cli` | verificado | `/api/health` respondió por HTTP real y los 15 tests Python pasaron. |
| BOOT-BE-003 | S1.06-S1.08 | `backend_cli` | verificado | `voz` levantó Uvicorn en loopback, sirvió la UI y apagó limpio con Ctrl+C; navegador cubierto por tests. |
| BOOT-BE-004 | S1.09 | `backend_cli` | verificado | Las tres pruebas de rutas XDG pasaron. |
| BOOT-WEB-001 | S1.04 | `frontend_web` | verificado | React/Vite compiló y el bundle quedó incluido en el wheel Python. |
| BOOT-WEB-002 | S1.13, S1.14 | `frontend_web` | verificado | ESLint y TypeScript strict pasaron después de `npm ci`. |
| BOOT-WEB-003 | S1.15 | `frontend_web` | verificado | Vitest ejecutó las dos pruebas de Home y health sin fallos. |
| BOOT-DOC-001 | S1.17, S1.18 | `docs_governance` | verificado | Reglas y roadmap creados; estructura, IDs y Markdown comprobados. |
| BOOT-DOC-002 | S1.20, S1.21 | `docs_governance` | verificado | ADR-0001 y setup Bazzite creados; enlaces y estructura comprobados. |
| BOOT-DOC-003 | S16.01 | `docs_governance` | verificado | README creado sin afirmar ASR implementado; enlaces comprobados. |
| BOOT-VERIFY-001 | S1.22 | `root` | verificado | Checkout limpio en Bazzite: locks, checks, Home/API HTTP y apagado limpio verificados. |

Cuando un paquete termine, conserva su fila como historial breve hasta el
siguiente corte coordinado; después puede moverse a un changelog de trabajo sin
alterar los IDs.

## Trabajo activo — Sección 2

| Paquete | IDs | Agente | Estado | Último logro verificable |
| --- | --- | --- | --- | --- |
| DOM-CORE-001 | S2.01-S2.03 | `domain_core` | verificado | Project, MediaAsset y Transcript: 39 pruebas focalizadas y checks estrictos pasan. |
| DOM-TIME-001 | S2.04, S2.05 | `timeline_models` | verificado | Segment y Word validan offsets/pertenencia; suite de dominio integrada pasa. |
| DOM-JOB-001 | S2.08-S2.10 | `job_state` | verificado | Pipeline, fallo y cancelación explícitos; suite de dominio integrada pasa. |
| DOM-SPEAKER-001 | S2.06, S2.07 | `timeline_models` | verificado | Speaker rename monotónico y SpeakerTurn acústico separado; 28 pruebas pasan. |
| PERSIST-PORT-001 | S2.11 | `domain_core` | verificado | Ocho Protocols no exponen SQL/Session; tests estructurales pasan. |
| PERSIST-REPO-001 | S2.12 | `domain_core` | verificado | 24 pruebas: adapters Core, sync Words y validación contra Segment padre. |
| PERSIST-MIG-001 | S2.13 | `backend_cli` | verificado | Upgrade/downgrade y wheel instalado con config/revisión Alembic pasan. |
| PERSIST-WAL-001 | S2.14 | `job_state` | verificado | 6 pruebas file-backed pasan: WAL, FK, timeout y reapertura real. |
| VERIFY-DOM-001 | S2.15 | `job_state` | verificado | 198 pruebas unitarias; arquitectura limpia, Ruff y Pyright pasan. |
| VERIFY-SQL-001 | S2.16, S2.17 | `job_state` | verificado | 16 pruebas file-backed cubren 8 adapters y recuperación tras reapertura. |

## Trabajo activo — Sección 3

| Paquete | IDs | Agente | Estado | Último logro verificable |
| --- | --- | --- | --- | --- |
| INGEST-PROBE-001 | S3.01-S3.03 | `media_probe` | verificado | 9 pruebas validan port, ffprobe real, streams/codecs y extensión irrelevante. |
| INGEST-STORE-001 | S3.04 | `media_import` | verificado | 13 pruebas validan copia inmutable, SHA-256 durante copia y publicación segura. |
| INGEST-FIX-001 | S3.11-S3.13 | `media_fixtures` | verificado | 6 fixtures sintéticos licenciados pasan hash, ffprobe y decodificación FFmpeg. |
| INGEST-APP-001 | S3.05, S3.06, S3.14 | `s3_import_reaudit` | verificado | 30 pruebas focales cubren copia inmutable, metadata persistida, corruptos y rollback ante interrupción. |
| INGEST-NORM-001 | S3.07, S3.10, S3.15 | `s3_normalizer_close` | verificado | 16 pruebas cubren PCM mono 16 kHz, cancelación, fsync, cierre de pipes y cleanup observable. |
| INGEST-PROGRESS-001 | S3.09 | `cold_norm_audit` | verificado | El progreso es monotónico, acotado y termina en la duración conocida. |
| INGEST-PROBE-FIX-001 | S3.03 | `ingest_audit2` | verificado | Regresiones cubren alias dca/dts y duraciones extremas sin excepción cruda. |
| INGEST-STORE-FIX-001 | S3.08, S3.16 | `s3_storage_reaudit` | verificado | 49 pruebas cubren reapertura, jerarquía durable, UUID, symlinks, nombres inseguros y cierre de descriptores. |

## Trabajo activo — Sección 4

| Paquete | IDs | Agente | Estado | Último logro verificable |
| --- | --- | --- | --- | --- |
| ASR-CONTRACT-001 | S4.01, S4.02 | `root` | verificado | Contrato path-free con cancelación y errores tipados; descriptor inmutable; suite completa de 349 pruebas pasa. |
| ASR-REGISTRY-001 | S4.03 | `root` | verificado | Registry determinista rechaza duplicados, contratos incompletos y entrypoints no invocables; checks estrictos pasan. |
| ASR-ADAPTER-001 | S4.04-S4.06 | `root` | verificado | Adapter local-only, instalación XDG confirmada y manifest de procedencia; 358 pruebas y checks estrictos pasan. |
| ASR-PROFILE-001 | S4.07-S4.09 | `root` | verificado | Descriptores fast/quality y fallback GPU/CPU con causa observable; 366 pruebas y checks estrictos pasan. |
| ASR-CHUNK-001 | S4.10, S4.11 | `root` | verificado | Planner con overlap/ownership y progreso por unidad; 373 pruebas y checks estrictos pasan. |
| ASR-RECOVERY-001 | S4.12-S4.14 | `root` | verificado | Checkpoints fijan plan/modelo/source/revisión/idioma; cancelación y reapertura no repiten chunks; rollback atómico probado. |
| ASR-CONTRACT-002 | S4.15-S4.17 | `root` | verificado | Suite común sobre provider estructural y Faster Whisper: WAV válido, timeline, cancelación y errores; integración física por clips. |
| ASR-LANGUAGE-001 | S4.18 | `root` | verificado | Idioma solicitado y detectado sobreviven checkpoints SQLite y reanudación; 400 pruebas pasan, 1 smoke real queda opt-in. |
| ASR-SANITIZE-001 | S4.04, S4.13 | `root` | verificado | Corte A: sustitución sin engines retenidos, cierre explícito y cancelación incluso con iterable vacío; 424 pruebas backend pasan, 1 smoke opt-in omitido, checks estrictos y frontend verde. |

---

## Trabajo activo — Sección 5

| Paquete | IDs | Agente | Estado | Último logro verificable |
| --- | --- | --- | --- | --- |
| OPTIONS-B1-001 | S5.18 | `root` | verificado | Consulta y GET /api/transcription-options sin cargas/descargas: registro, runtime, ejecución, IDs y recomendación separados; 452 pruebas backend, 1 smoke omitido y checks/backend/frontend verdes. |
| OPTIONS-UI-001 | S5.19 | `frontend_selector` | verificado | Selector radio accesible sobre B1 con razones de bloqueo traducidas y recomendación; 7 tests Vitest, montado en App; lint/typecheck/build verdes. |
| PROJECTS-API-001 | S5.01 (backend) | `projects_api` | verificado | CreateProject/ListProjects y POST/GET /api/projects cableados en create_app con migración Alembic al arrancar; 24 tests + smoke HTTP real. |
| MEDIA-UPLOAD-001 | S5.02, S5.03 (backend) | `media_upload_api` | verificado | POST /api/projects/{id}/media por body crudo → ImportMedia real (SHA-256, ffprobe), 400/404/413/415/422/503 tipados, temporal limpiado; 18 tests + smoke HTTP con fixture WAV. |
| JOBS-CORE-001 | S5.20, S14.01, S14.08 | `jobs` | verificado | CreateTranscriptionJob revalida option_id y guarda snapshot (migración 0003); JobRunner en hilo con recover() al arrancar, cancel entre chunks y PERSISTING idempotente; POST/GET/cancel jobs y GET segmentos cableados; 18 tests + smoke HTTP (409 option_not_startable sin modelo). Flujo con modelo real sigue experimental. |
| JOBS-SSE-001 | S5.06 | `sse_events` | verificado | GET /api/jobs/{id}/events por StreamingResponse con sondeo en thread, keep-alive y `end` terminal; hook useJobEvents; 6+6 tests, montado en create_app y App. |
| UI-IMPORT-001 | S5.01, S5.02, S5.03 (UI) | `frontend_import` | verificado | NewProjectCard: nombre, drop nativo, XHR con progreso y errores por código; 6 tests; montada en App y verificada contra backend real por smoke. |
| UI-JOB-001 | S5.04, S5.05, S5.07 | `frontend_job` | verificado | JobScreen por etapa, cancelar y SegmentList montados en App sobre POST /api/jobs + SSE; 18 tests Vitest; camino 409 verificado en vivo; ejecución con modelo real pendiente del smoke opt-in. |
| EXPORT-TEXT-001 | S10.01, S10.02, S10.03, S10.09, S10.10 | `export_text` | verificado | Protocol TranscriptExporter estructural, TXT literal, Markdown y safe_export_filename anti-traversal; 51 golden tests inline. |
| EXPORT-SUBS-001 | S10.04, S10.05, S10.06, S10.11, S10.12, S10.13 | `export_subs_json` | verificado | SRT, VTT, timestamps con límites, JSON canónico voz.transcript v1 y round-trip parse(render(x)); 34 tests. |
| OSS-DOCS-001 | S16.03-S16.08, S16.17, S16.18 | `docs_oss` | verificado | CONTRIBUTING, CODE_OF_CONDUCT (Covenant 2.1), SECURITY, plantillas issue/PR, licencias de fixtures y NOTICE con licencias verificadas; enlaces comprobados. |
| DOCTOR-CLI-001 | S8.12, S8.13 | `doctor_cli` | verificado | `voz doctor` (texto/--json/--redact): ffmpeg/ffprobe, puerto, rutas XDG, disco, runtime ASR y GPU sin cargar modelos; 12 tests + ejecución real; `voz` sin subcomando sigue sirviendo. |
| UI-PLAYER-001 | S5.08, S5.10 | `media_player` | verificado | GET /api/media/{id}/original con FileResponse (Range 206/416, sin paths) y AudioPlayer nativo con seek desde SegmentList; 5 tests backend + 8 frontend; smoke HTTP 200/206 en vivo. |
| SEGMENTS-EDIT-001 | S5.12 (backend) | `segments_edit_api` | verificado | PUT /api/segments/{id} con revisión optimista (UPDATE condicional), original_text preservado, migración 0004 conserva words; smoke 404 real. |
| EXPORT-HTTP-001 | S10.07, S10.08, S10.14 | `export_http` | verificado | GET /api/transcripts/{id}/export 5 formatos, filename* RFC 5987, agrupado por speaker y tiempos opcionales; 17 tests HTTP + goldens; ExportMenu montado. |
| WAVEFORM-001 | S5.09, S5.14 | `waveform` | verificado | Peaks FFmpeg en streaming (1 h WAV en 0,86 s, 70 MB RSS), cache XDG atómica, canvas con zoom 1–32x y seek por clic/teclado; smoke 200/422. |
| TRANSCRIPT-VIEW-001 | S5.11, S5.13, S5.15 | `transcript_view` | verificado | Segmento activo por búsqueda binaria, autoscroll pausable, búsqueda sin tildes con navegación; content-visibility + filas memo (10k segmentos, 2 renders por cambio). |
| SEGMENT-EDITOR-001 | S5.12 (UI), S5.16 | `segment_editor_ui` | verificado | Borradores fuera de filas, debounce 800 ms + blur, PUT serializado por segmento, conflicto 409 resoluble, AutosaveStatus global; 29 tests. |
| ARCH-DOCS-001 | S16.09-S16.11 | `docs_arch` | verificado | docs/architecture C4 (contexto, contenedores, componentes) en Mermaid; 83 enlaces y 124 rutas comprobados. |
| ARCH-ADR-001 | S16.12-S16.16 | `docs_arch` | verificado | ADR-0001–0004 completados con evidencia; ADR-0005 providers y ADR-0006 local-first nuevos. |
| ROBUST-001 | S14.03, S14.12, S14.14 | `robustness` | verificado | 507 disk_space_insufficient en upload/normalización, fuzz ffprobe (2 bugs corregidos), resume idempotente (2 bugs del runner corregidos); 739 tests. |
| MODELS-CATALOG-001 | S8.01-S8.03 | `model_catalog` | verificado | Catálogo de 6 modelos con revisión, tamaños y SHA-256 verificados contra HuggingFace; GET /api/models con instalado/tamaño; turbo recomendado. |
| MODELS-ADMIN-001 | S8.07, S8.08 | `model_catalog` | verificado | DELETE /api/models/{id}?confirm= con 409 model_in_use; uso de disco por modelo y libre; tests HTTP. |
| MODELS-STORE-001 | S8.04-S8.06 | `model_store` | verificado | Descarga stdlib con progreso, cancelación y SHA-256/tamaño por archivo contra servidor HTTP local; 37 tests. |
| MODELS-STORE-002 | S8.15, S14.04, S14.09 | `model_store` | verificado | Reanudación Range, .part corrupto descartado, instalado incoherente se reemplaza, espacio previo con disk_space_insufficient. |
| MODELS-BUZZ-001 | S8.09, S8.10 | `buzz_cache` | verificado | Detección solo-lectura del Flatpak real de Buzz (turbo y large-v3) e importación por hardlink en 1,4 s con SHA-256; árbol de Buzz intacto. |
| E2E-001 | S5.17 | `e2e` | verificado | Flujo HTTP completo con runner real (import→job→SSE→Range→peaks→edición 409→export→reinicio) + App con fetch/XHR/SSE simulados; bug de resaltado corregido. |
| PKG-001 | S15.01-S15.03 | `packaging` | verificado | 3 builds idénticos con SOURCE_DATE_EPOCH; wheel roto por .gitignore (transcript.py) corregido; uv tool install ejecuta voz y doctor. |
| PKG-002 | S15.04, S15.05 | `packaging` | verificado | Wheel con static y migraciones 0001–0004 (test); instalado fuera del checkout sirve / y /api/health. |
| PKG-003 | S15.07-S15.09, S15.11 | `packaging` | verificado | scripts/checksums.sh, CHANGELOG Keep a Changelog, docs/release.md con semver/API pública, docs/install/linux.md. |
| DIAG-001 | S14.10, S14.11, S8.14 | `diagnostics` | verificado | Backup sqlite antes de migrar (5 retenidos, aborta si falla), voz doctor --bundle redactado, checks de disco/modelos/keys set|unset. |
| MODELS-TASKS-001 | S8.04 (UI), S8.05 (UI) | `model_tasks_api` | verificado | ModelTaskRunner FIFO con progreso/cancelación; POST /api/models/{id}/install con confirmación, /api/model-tasks; test contra store real y http.server local. |
| MODELS-UI-001 | S8.02 (UI), S8.03 (UI), S8.07 (UI) | `model_manager_ui` | verificado | Sección Modelos montada: tamaño previo, importar desde Buzz, descarga con <dialog>, progreso, cancelar, borrado tecleando el id; selector ordenado y refrescado. |
| HW-RECOMMEND-001 | S8.11, S14.05, S14.06 | `hardware_recommend` | verificado | nvidia-smi/meminfo sin shell; turbo recomendado con VRAM ≥ 6 GiB, small/base en CPU; 409 insufficient_vram/ram antes de crear job. |
| DIAR-CORE-001 | S6.01, S6.02, S6.08 | `diarization_core` | verificado | Port DiarizationProvider, cluster≠Speaker con paleta persistente, reconciliación por solape máximo; AssignSpeakers idempotente conserva renombres. |
| DIAR-CORE-002 | S6.14 | `diarization_core` | verificado | 17 casos de reconciliación: overlap, silencio, turn que cruza segmentos, bordes, desorden y 0 turns. |
| DIAR-SHERPA-001 | S6.16, S6.04 | `diarization_sherpa` | verificado | Modelos ONNX descargados de verdad desde GitHub con SHA-256 verificado; adapter sherpa-onnx real separa A/B/A en diálogo sintético; ADR-0007. |
| DIAR-SHERPA-002 | S6.05-S6.07 | `diarization_sherpa` | verificado | Real: automático y exacto=2 → A/B/A; rango 1–1 re-ejecuta recortado a 1 speaker sin recargar modelos. |
| WORDS-001 | S7.01, S7.03, S7.04 | `word_timestamps` | verificado | AlignmentProvider sin implementación extra; ADR-0008 (nativo faster-whisper, WhisperX no evaluado); Words persistidas con uuid5 y clamp; API words ([] si editado). |
| WORDS-002 | S7.08, S7.09 | `word_timestamps` | verificado | Fallback sin palabras completa el job; checkpoints viejos compatibles; monotonicidad, clamp y overlap sin duplicar probados; 1011 tests. |
| DIAR-PIPE-001 | S6.13, S6.15, S14.07 | `diarization_pipeline` | verificado | Etapa DIARIZING opcional por job (migración 0005), ASR liberado antes de diarizar, fallo de diarización no pierde el transcript; runner con sherpa real sobre diálogo pasa. |
| SPEAKERS-001 | S6.09-S6.11 | `speakers_ui_api` | verificado | GET/PATCH/merge de speakers con color y nombre persistentes, fusión transaccional; SpeakersPanel montado; 19 tests HTTP. |
| SPEAKERS-002 | S6.12 | `speakers_ui_api` | verificado | PUT /api/segments/{id}/speaker y SegmentSpeakerSelect por fila; la lista recarga sin perder búsqueda (reloadKey). |
| WORDS-003 | S7.05 | `word_ui` | verificado | Speaker por palabra según el turn de su punto medio, calculado al vuelo en la vista (SpeakerTimeline). |
| WORDS-UI-001 | S7.06, S7.07 | `word_ui` | verificado | WordText con seek por clic/teclado y palabra actual vía store externo (solo re-renderiza 2 palabras); modo Leer/Editar. |
| CLOUD-SECRETS-001 | S11.01 | `openai_provider` | verificado | ProviderSecrets: env o secrets.toml 0600 atómico, nunca en SQLite/logs (tests); /api/providers sin eco de la clave. |
| OPENAI-001 | S11.02, S11.05, S11.06 | `openai_provider` | verificado | Adapter whisper-1 con división bajo 25 MB y offsets globales sin solapes; transporte fake (experimental, no verificado contra el servicio). |
| OPENAI-002 | S11.03, S11.04, S11.07 | `openai_provider` | verificado | gpt-4o-transcribe-diarize con speaker, límites fechados, backoff solo 429/5xx/timeout. |
| OPENAI-003 | S11.08, S11.10, S11.11 | `openai_provider` | verificado | Estimación de coste por endpoint, FakeOpenAITransport y casos openai en la suite de contrato común. |
| OPENAI-004 | S11.12, S11.13 | `openai_provider` | verificado | docs/privacy/openai.md; sin clave no inicia, con clave nunca recomendado ni fallback (tests de 0 requests). |
| ELEVEN-001 | S12.01-S12.03 | `elevenlabs_provider` | verificado | Clave vía ProviderSecrets, adapter Scribe v1 y segmentos con speaker (transporte fake; experimental). |
| ELEVEN-002 | S12.04-S12.06 | `elevenlabs_provider` | verificado | Palabras en ms monótonos, keyterms acotados, progreso y cancelación de subida sin reintentos que facturen doble. |
| ELEVEN-003 | S12.07-S12.09 | `elevenlabs_provider` | verificado | Precio fechado reutilizando el endpoint de estimación; fake client y contrato común. |
| ELEVEN-004 | S12.10, S12.11 | `elevenlabs_provider` | verificado | docs/privacy/elevenlabs.md y test estructural: el adapter solo vive en infrastructure/cloud. |
| WCPP-001 | S9.01, S9.02, S9.05 | `whispercpp_provider` | verificado | WhisperCppProvider con binario fake, detección validada por --help y 6 modelos ggml fijados con SHA-256. |
| WCPP-002 | S9.06-S9.08 | `whispercpp_provider` | verificado | JSON -ojf a segmentos/palabras, cancelación mata el proceso, errores tipados; suite de contrato común pasa. |
| WCPP-003 | S9.03, S9.04, S9.09 | `whispercpp_provider` | verificado | docs/whisper-cpp.md (CUDA/Vulkan, documentado no verificado aquí) y sugerencia visible nunca automática; opciones solo si existe whisper-cli. |
| ROBUST-002 | S14.02, S14.13 | `robustness2` | verificado | 18 escrituras críticas auditadas (synchronous=FULL, fsync antes de replace) y cierre/reapertura a mitad de job sin repetir chunks. |
| PKG-004 | S15.10 | `robustness2` | verificado | Clone limpio en Bazzite: uv tool install, extra asr-local con CUDA float16 y servidor verificados; docs corregidas. |
| OSS-AUDIT-001 | S16.19 | `robustness2` | verificado | scripts/audit-secrets.sh sobre árbol e historial: 0 HIGH; decisión de correo de autor pendiente antes de publicar. |
| QUALITY-FLAGS-001 | S13.04, S13.05, S13.12 | `quality_flags` | verificado | Métricas avg_logprob/no_speech/compression desde faster-whisper; flags repetition, silence_hallucination, out_of_bounds, low_confidence (puros, nunca tocan el texto); migración 0006 quality_json; API `quality`; regla S13.12 en docs/api/segments.md. |
| QUALITY-REVIEW-001 | S13.06 | `quality_flags` | verificado | ReviewQueue: "N segmentos por revisar", filtro por tipo, anterior/siguiente con seek, marcar revisado (local a la sesión); filas con ⚠ accesible. |
| BENCH-001 | S13.08-S13.10 | `benchmark` | verificado | `voz bench`: carga, RTF, pico RSS y VRAM (nvidia-smi), --json; dataset solo en XDG (rechaza dentro del checkout); WER/CER stdlib con normalización documentada. |
| BENCH-002 | S13.07 | `benchmark` | verificado | Medido en RTX 4060: turbo CUDA RTF 0,025 WER 1,66 %; large-v3 RTF 0,073 WER 1,99 % (8,14 % en clip largo); ver docs/benchmarks.md (audio sintético). |
| WCPP-004 | S9.10 | `benchmark` | verificado | whisper.cpp v1.9.4 compilado (CPU), ggml q5_0 con sha256 verificado: RTF 0,80 WER 1,83 %; JSON real de -ojf como fixture y test del adapter. |
| CLOUD-UI-001 | S11.09 | `cloud_ui` | verificado | Badge CLOUD antes/durante/después, consentimiento obligatorio, estimación de costo, claves desde la UI sin mostrarlas; nombres/privacidad vienen del backend (S12.11 intacto). |
| MODELS-UI-002 | (completa S8) | `models_ui2` | verificado | Claves `proveedor:modelo`; ManagedModelCatalog + RoutingModelStore: faster-whisper, whisper.cpp (si hay whisper-cli) y diarization:sherpa-default con descarga/borrado; smoke HTTP real OK. |
| PKG-005 | S15.06 | `packaging2` | verificado | .github/workflows/release-dry-run.yml: build reproducible, checksums, install check, artifact 7 días, contents: read, sin publicar (no ejecutado: requiere push). |
| PKG-006 | S15.12, S15.13 | `packaging2` | verificado | Prototipos medidos: AppImage base 46 MiB (arranque ~1 s), asr-local 1,42 GiB con CUDA; Flatpak base 52,6 MB instalado, asr-local 2,8 GB; recomendación en docs/packaging/appimage-flatpak.md. |
| QUALITY-CORE-001 | S13.01 | `quality_core` | verificado | Glosario por proyecto (≤50 términos; migración 0007) congelado en la selección del job; a faster-whisper como `hotwords` y a keyterms del proveedor cloud; smoke real en RTX 4060 con "VOZ"/"presupuesto" transcritos. |
| QUALITY-CORE-002 | S13.02, S13.03, S13.11 | `quality_core` | verificado | Perfiles `default`/`academic` v1 inmutables guardados completos en la selección; VAD por perfil (smoke real con academic+VAD OK); `GET /api/quality-profiles?language=` recomienda solo con mediciones (es/default, sintético) y dice "sin medición" en lo demás. |
| INTEGRITY-001 | (riesgos) | `integrity` | verificado | Etiquetas `speaker` de proveedores cloud → entidades Speaker idempotentes (la diarización local gana); job y selección en una transacción (`add_with_selection`) con test de rollback. |
| DOCS-DEMO-001 | S16.02 | `docs_demo` | verificado | `scripts/capture-screenshots.sh`: XDG temporal, turbo importado de Buzz, transcripción real en GPU y 7 capturas por CDP con Chrome flatpak headless; docs/demo.md y README. |

### Retomar en una sesión nueva

Leer `AGENTS.md`, este tablero, `.ai/HANDOFF.md` y `.ai/CHECKLIST.md` si
existen, y los contratos en `docs/api/`; comprobar Git y las validaciones antes
de editar. Oleada 3 (2026-09-30) cerró S5 salvo S5.17 (E2E), S10 completa,
S14.03/12/14 y S16.09–S16.16. Oleada 4a cerró S5.17, S8 casi completa (falta
S8.11), S14.04/09/10/11 y packaging. Oleada 4b+5a cerró Model Manager en UI,
S8.11, S14.05/06, núcleo y adapter de diarización (sherpa-onnx) y palabras.
Oleada 5b cerró S6 (salvo S6.03), S7 (salvo S7.02), S9 (salvo S9.10),
S11 (salvo S11.09), S12, S14.02/07/13, S15.10 y S16.19. Siguiente (5c): S13
calidad, badge CLOUD (S11.09), S15.06, S16.02.


Desde 2026-10-10 el trabajo activo es el Programa V (marca V, endurecimiento,
documentación en inglés, TTS y release). Para retomar, leer
`.ai/v-plan/HANDOFF.md`, `.ai/v-plan/STATUS.md` y
`.ai/v-plan/AGENT-PROTOCOL.md` (privados, fuera de Git). Línea base: HEAD
1186908 = `origin/main`; pytest 1612 passed / 3 skipped, vitest 543.

## Voice engine extensions

| Slice | State | Scope |
| --- | --- | --- |
| V5-05 | Verified | Keyboard focus and sample cancellation regressions fixed; Carbon/M3, light/dark and es/en verified at 390 px with deterministic browser inputs. |
| V6-05a | Verified | Explicit custom-model previews and confirmed background imports, pinned hashes, isolated load validation, live options and confirmed deletion; fake HTTP and default-wiring tests verified. |
| V8-01 | Verified | ADR-0011 defines experiment-only resource controls and separates measured results from estimates; executor remains planned. |
| V5-04 | Verified | Persistent synthesis history with playback, WAV downloads and confirmed deletion, including when no models are installed; UI and static-bundle browser flow verified. |
| V4-04 | Verified | Configurable STT/TTS servers, explicit CLOUD consent, private endpoint storage and safe validation errors; fake HTTP contracts and browser flow verified. |

## Trabajo activo — v3 y portable

| Paquete | IDs | Agente | Estado | Último logro verificable |
| --- | --- | --- | --- | --- |
| PORT-001 | S15.15-S15.18 | `root` | verificado | Windows/macOS/Linux con doble clic, segundo doble clic reutiliza servidor y acceso directo de escritorio; PWA instalable sin test (S15.17 abierto). |
| UI-V2-001 | S5.27-S5.30 | `root` | verificado | Editor, progreso por etapa con ETA, cerrar servidor, temas Carbon e i18n es/en. |
| API-V3-001 | S5.32, S6.17-S6.19, S14.15-S14.16 | `root` | verificado | `GET /api/library`, renombrar/eliminar proyecto y `rediarize`: `tests/integration/test_library_projects_api.py`, `tests/integration/application/test_rediarize.py`. |
| UI-V3-001 | S5.21-S5.26 | `root` | verificado | Home/biblioteca, rutas por hash, revisión que salta al audio, exportar con vista previa, volumen hasta 300 % y panel de hablantes. |
| UI-M3-001 | S5.31 | `root` | verificado | Piel Material 3 seleccionable en Ajustes; CI verde en 3 SO (1186908). |

## Sección 1 — Bootstrap del repositorio

- [x] **S1.01** Inicializar el repositorio con la estructura base acordada.
- [x] **S1.02** Elegir y añadir una licencia válida.
- [x] **S1.03** Crear `pyproject.toml` administrado con `uv` y Python 3.12.
- [x] **S1.04** Crear el frontend React, TypeScript y Vite.
- [x] **S1.05** Exponer un FastAPI mínimo con `GET /api/health`.
- [x] **S1.06** Crear el punto de entrada Typer `voz`.
- [x] **S1.07** Hacer que `voz` inicie Uvicorn en loopback.
- [x] **S1.08** Hacer que `voz` abra el navegador, salvo `--no-browser`.
- [x] **S1.09** Definir rutas XDG para config, datos, cache y estado.
- [x] **S1.10** Configurar Ruff para lint y formato backend.
- [x] **S1.11** Configurar el type checker backend.
- [x] **S1.12** Configurar pytest y una prueba de `/api/health`.
- [x] **S1.13** Configurar ESLint para el frontend.
- [x] **S1.14** Activar TypeScript strict y su comando de comprobación.
- [x] **S1.15** Configurar Vitest y una prueba mínima de Home.
- [x] **S1.16** Crear CI inicial para checks backend y frontend.
- [x] **S1.17** Crear `AGENTS.md` con reglas estables y comandos.
- [x] **S1.18** Crear este roadmap con IDs y seguimiento atómico.
- [x] **S1.19** Crear `.ai/` local y asegurar sus exclusiones de Git.
- [x] **S1.20** Registrar ADR-0001 del monolito modular.
- [x] **S1.21** Documentar el setup de desarrollo en Bazzite.
- [x] **S1.22** Verificar instalación limpia, arranque de `voz` y Home local en Bazzite.

**Criterio de salida:** desde un checkout limpio se instala el proyecto, se
ejecuta `voz` y se ve la UI local. No instalar Whisper en esta sección.

## Sección 2 — Dominio y persistencia

- [x] **S2.01** Modelar `Project` con identidad e invariantes.
- [x] **S2.02** Modelar `MediaAsset` sin rutas expuestas a la UI.
- [x] **S2.03** Modelar `Transcript`.
- [x] **S2.04** Modelar `Segment` con offsets válidos.
- [x] **S2.05** Modelar `Word` con offsets válidos.
- [x] **S2.06** Modelar `Speaker` editable.
- [x] **S2.07** Modelar `SpeakerTurn` separado de identidad acústica.
- [x] **S2.08** Modelar la máquina de estados de `TranscriptionJob`.
- [x] **S2.09** Probar transiciones válidas de jobs.
- [x] **S2.10** Probar rechazo de transiciones inválidas.
- [x] **S2.11** Definir ports de repositories.
- [x] **S2.12** Implementar repositories SQLite.
- [x] **S2.13** Crear migración Alembic inicial.
- [x] **S2.14** Activar SQLite WAL mediante el adapter.
- [x] **S2.15** Añadir pruebas unitarias de entidades e invariantes.
- [x] **S2.16** Añadir pruebas de integración de repositories SQLite.
- [x] **S2.17** Verificar recuperación de proyectos y jobs tras reinicio.

**Criterio de salida:** proyectos y jobs sobreviven un reinicio sin que el
dominio dependa de SQLite.

## Sección 3 — Ingestión multimedia

- [x] **S3.01** Definir `MediaProbePort`.
- [x] **S3.02** Implementar el adapter ffprobe.
- [x] **S3.03** Validar por streams/codecs y no solo por extensión.
- [x] **S3.04** Copiar el original de forma segura e inmutable.
- [x] **S3.05** Calcular y persistir el hash del original.
- [x] **S3.06** Extraer duración, codec, sample rate y channels.
- [x] **S3.07** Normalizar a audio mono de 16 kHz para inferencia.
- [x] **S3.08** Conservar reproducción/exportación desde el original.
- [x] **S3.09** Reportar progreso de normalización.
- [x] **S3.10** Cancelar la normalización sin dejar artefactos corruptos.
- [x] **S3.11** Añadir fixture WAV con licencia compatible.
- [x] **S3.12** Añadir fixtures MP3 y M4A con licencia compatible.
- [x] **S3.13** Añadir fixtures OGG, OPUS y WebM con licencia compatible.
- [x] **S3.14** Mapear archivo corrupto a error tipado.
- [x] **S3.15** Limpiar temporales de éxito, fallo y cancelación.
- [x] **S3.16** Probar import contra path traversal y nombres inseguros.

**Criterio de salida:** VOZ ingiere formatos comunes que FFmpeg puede decodificar
y genera audio normalizado reproducible sin modificar el original.

## Sección 4 — Primer ASR local

- [x] **S4.01** Definir el port `TranscriptionProvider`.
- [x] **S4.02** Definir `ModelDescriptor` y sus capacidades.
- [x] **S4.03** Crear el provider registry sin imports en dominio.
- [x] **S4.04** Implementar el adapter Faster Whisper.
- [x] **S4.05** Implementar descarga explícita de un modelo local.
- [x] **S4.06** Registrar revisión y procedencia del modelo.
- [x] **S4.07** Implementar perfil `fast` por descriptor.
- [x] **S4.08** Implementar perfil `quality` por descriptor.
- [x] **S4.09** Detectar GPU y elegir fallback CPU explícito.
- [x] **S4.10** Planificar chunks con offsets globales.
- [x] **S4.11** Reportar progreso por chunk.
- [x] **S4.12** Persistir un resultado parcial verificado.
- [x] **S4.13** Cancelar ASR entre unidades recuperables.
- [x] **S4.14** Reanudar desde checkpoints sin repetir chunks completos.
- [x] **S4.15** Añadir contract test de audio válido.
- [x] **S4.16** Añadir contract test de timestamps monótonos y no negativos.
- [x] **S4.17** Añadir contract test de cancelación y errores mapeados.
- [x] **S4.18** Preservar metadata de idioma en el resultado canónico.

**Criterio de salida:** un archivo largo puede transcribirse localmente y
reanudarse bajo el contrato común.

Smoke real 2026-09-30 (RTX 4060 Laptop, CUDA float16 vía wheels nvidia del
extra `asr-local`): turbo y large-v3 importados del cache de Buzz pasan el
smoke opt-in, y el flujo HTTP completo transcribe 25 s de español en ~3 s.
El flujo local, el recorte físico por chunks y la recuperación están verificados
con el adapter real y un engine determinista. El runtime/modelo Faster Whisper
real permanece experimental hasta ejecutar el smoke opt-in con un modelo que el
usuario haya elegido e instalado explícitamente; no se descargan pesos en tests.

Corrección S4.04/S4.13 (Corte A, 2026-09-07): regresiones con weakrefs y events
verifican liberación antes de cargar otro engine, fallo de carga coherente,
cierre idempotente/serializado, limpieza de tracebacks SDK y cancelación del
provider aislado. ADR-0004 documenta el lifecycle y sus límites. No se abren IDs
nuevos ni se modifica la calificación experimental del runtime/CUDA.

## Sección 5 — Workspace UI

- [x] **S5.01** Crear Home con acción “Nuevo proyecto”.
- [x] **S5.02** Implementar selección y drag-and-drop de archivo.
- [x] **S5.03** Mostrar validación de upload y errores seguros.
- [x] **S5.04** Crear pantalla de job.
- [x] **S5.05** Mostrar estado explícito por etapa.
- [x] **S5.06** Consumir progreso mediante SSE.
- [x] **S5.07** Renderizar lista de segmentos.
- [x] **S5.08** Añadir reproductor del original.
- [x] **S5.09** Renderizar waveform.
- [x] **S5.10** Hacer seek al seleccionar un timestamp.
- [x] **S5.11** Sincronizar selección/autoscroll con playback.
- [x] **S5.12** Editar y guardar texto de un segmento.
- [x] **S5.13** Buscar texto en el transcript.
- [x] **S5.14** Controlar zoom del waveform.
- [x] **S5.15** Virtualizar transcripts largos.
- [x] **S5.16** Añadir autosave con estado visible.
- [x] **S5.17** Probar importación, reproducción y edición E2E.
- [x] **S5.18** Exponer opciones canónicas de transcripción mediante consulta backend.
- [x] **S5.19** Implementar selector básico frontend, sin Model Manager.
- [x] **S5.20** Persistir selección reproducible para creación de job.
- [x] **S5.21** Home con biblioteca de transcripciones: abrir, renombrar y eliminar (`apps/web/src/components/Library.test.tsx`).
- [x] **S5.22** Rutas por hash con enlace propio por transcripción y Atrás/recargar (`apps/web/src/lib/navigation.test.ts`).
- [x] **S5.23** La cola de revisión salta al segmento y al audio (`ReviewQueue.test.tsx`, `SegmentList.test.tsx`).
- [x] **S5.24** Exportar con vista previa, tiempos y agrupar por hablante (`apps/web/src/App.flows.test.tsx`).
- [x] **S5.25** Audio con volumen hasta 300 %, velocidad y atajos (`AudioPlayer.test.tsx`).
- [x] **S5.26** Panel de hablantes con tiempo de habla, filtro y muestra (`SpeakersPanel.test.tsx`, `lib/speakerTurns.test.ts`).
- [x] **S5.27** Progreso por etapa con ETA y texto en vivo (`App.flows.test.tsx`, `tests/unit/test_job_views.py`).
- [x] **S5.28** Botón Cerrar servidor (`api/shutdown.test.ts`, `tests/integration/test_shutdown_api.py`).
- [x] **S5.29** Temas Carbon, acentos e i18n es/en (`i18n/i18n.test.ts`, `theme/appearance.test.ts`).
- [x] **S5.30** Editor de transcripción con línea de tiempo de hablantes (`App.flows.test.tsx`, `SegmentList.test.tsx`).
- [x] **S5.31** Piel Material 3 seleccionable en Ajustes (`theme/m3.test.ts`, `theme/appearance.test.ts`).
- [x] **S5.32** `GET /api/library` (`tests/integration/test_library_projects_api.py`).

S5.18–S5.20 consultan y seleccionan opciones conocidas; descargas, reparación,
checksums exhaustivos y administración avanzada permanecen en Sección 8.

**Criterio de salida:** el flujo básico de upload, progreso, reproducción y
edición es usable con una grabación larga.

## Sección 6 — Diarización

- [x] **S6.01** Definir el port `DiarizationProvider`.
- [x] **S6.02** Modelar clusters, speakers y assignments por separado.
- [ ] **S6.03** Implementar adapter pyannote Community-1. _(bloqueado: reemplazado por S6.16/ADR-0007; requiere torch y token HF; solo si Marshall lo pide)_
- [x] **S6.04** Implementar descarga/configuración explícita del modelo.
- [x] **S6.05** Ejecutar detección automática del número de speakers.
- [x] **S6.06** Permitir mínimo y máximo de speakers.
- [x] **S6.07** Permitir número exacto de speakers.
- [x] **S6.08** Reconciliar turns con segmentos ASR.
- [x] **S6.09** Asignar colores persistentes por speaker.
- [x] **S6.10** Renombrar speaker sin reejecutar modelos.
- [x] **S6.11** Fusionar speakers sin reejecutar ASR.
- [x] **S6.12** Reasignar un segmento manualmente.
- [x] **S6.13** Probar diarización con dos speakers.
- [x] **S6.14** Probar overlap y segmentos sin speaker.
- [x] **S6.15** Verificar liberación secuencial de VRAM entre ASR y diarización.
- [x] **S6.16** Implementar adapter sherpa-onnx local sin torch ni token (ADR-0007).
- [x] **S6.17** `POST /api/transcripts/{id}/rediarize` sin re-transcribir (`tests/integration/application/test_rediarize.py`).
- [x] **S6.18** Umbral medido y fusión de hablantes pequeños (`tests/unit/application/test_diarization_cleanup.py`, `test_speaker_matching.py`).
- [x] **S6.19** `talk_ms` y `first_ms` por hablante (`tests/integration/test_speakers_api.py`).

**Criterio de salida:** “quién dijo qué” se puede revisar y corregir sin volver a
transcribir.

## Sección 7 — Word timestamps y alignment

- [x] **S7.01** Definir el port `AlignmentProvider`.
- [ ] **S7.02** Evaluar WhisperX contra fixtures e idiomas objetivo. _(bloqueado: requiere torch ~3 GB; ADR-0008 eligió timestamps nativos)_
- [x] **S7.03** Documentar la decisión de adapter de alignment.
- [x] **S7.04** Persistir timestamps a nivel de palabra.
- [x] **S7.05** Reconciliar palabra con speaker.
- [x] **S7.06** Hacer seek al seleccionar una palabra.
- [x] **S7.07** Resaltar la palabra actual durante playback.
- [x] **S7.08** Implementar fallback cuando no exista aligner del idioma.
- [x] **S7.09** Probar monotonicidad y límites de word timestamps.

**Criterio de salida:** palabra y audio permanecen sincronizados donde haya
soporte, con degradación explícita donde no lo haya.

## Sección 8 — Model Manager

- [x] **S8.01** Definir catálogo canónico de modelos.
- [x] **S8.02** Mostrar estado installed/not installed.
- [x] **S8.03** Mostrar tamaño antes de descargar.
- [x] **S8.04** Descargar con progreso visible.
- [x] **S8.05** Permitir cancelación segura de descarga.
- [x] **S8.06** Verificar checksum o revisión disponible.
- [x] **S8.07** Eliminar un modelo con confirmación.
- [x] **S8.08** Mostrar uso de disco por modelo/proveedor.
- [x] **S8.09** Detectar cache de Buzz sin modificarlo.
- [x] **S8.10** Reutilizar/importar un modelo compatible sin mover el original.
- [x] **S8.11** Recomendar perfiles según hardware detectado.
- [x] **S8.12** Implementar `voz doctor` para FFmpeg y puertos.
- [x] **S8.13** Extender `voz doctor` para GPU/CUDA y runtime ASR.
- [x] **S8.14** Extender `voz doctor` para disco, modelos y API keys opcionales.
- [x] **S8.15** Probar descarga incompleta y recuperación.

**Criterio de salida:** el usuario administra modelos sin tocar carpetas
manualmente.

## Sección 9 — whisper.cpp

- [x] **S9.01** Implementar adapter whisper.cpp bajo el port común.
- [x] **S9.02** Detectar y validar el binario.
- [x] **S9.03** Documentar build/uso con CUDA.
- [x] **S9.04** Documentar build/uso con Vulkan.
- [x] **S9.05** Registrar modelos cuantizados compatibles.
- [x] **S9.06** Mapear salida a segmentos canónicos.
- [x] **S9.07** Mapear fallos/cancelación a errores comunes.
- [x] **S9.08** Pasar la suite completa de contract tests.
- [x] **S9.09** Implementar fallback automático solo cuando sea seguro y visible.
- [x] **S9.10** Comparar rendimiento CPU/GPU con fixtures controlados.

**Criterio de salida:** existe una segunda implementación local completa bajo el
mismo contrato.

## Sección 10 — Exportación

- [x] **S10.01** Definir el port/servicio de exportación.
- [x] **S10.02** Exportar TXT literal.
- [x] **S10.03** Exportar Markdown.
- [x] **S10.04** Exportar SRT con timestamps válidos.
- [x] **S10.05** Exportar VTT con timestamps válidos.
- [x] **S10.06** Exportar JSON canónico versionado.
- [x] **S10.07** Exportar agrupado por speaker.
- [x] **S10.08** Exportar texto con timestamps opcionales.
- [x] **S10.09** Sanitizar nombres y evitar path traversal.
- [x] **S10.10** Añadir golden tests TXT/Markdown.
- [x] **S10.11** Añadir golden tests SRT/VTT.
- [x] **S10.12** Añadir golden tests JSON.
- [x] **S10.13** Verificar round-trip del formato canónico cuando aplique.
- [x] **S10.14** Exponer exportación por HTTP con descarga segura.

**Criterio de salida:** exportaciones estables, seguras y reproducibles completan
el MVP junto con las Secciones 1–6.

## Sección 11 — OpenAI opcional

- [x] **S11.01** Diseñar configuración de API key fuera de SQLite y logs.
- [x] **S11.02** Implementar adapter de file transcription.
- [x] **S11.03** Implementar adapter de diarized transcription.
- [x] **S11.04** Detectar límites reales mediante configuración/versiones probadas.
- [x] **S11.05** Dividir archivos cuando el provider lo exija.
- [x] **S11.06** Reconstruir offsets globales sin solapamientos inválidos.
- [x] **S11.07** Implementar retries/backoff solo para fallos recuperables.
- [x] **S11.08** Estimar coste antes de enviar.
- [x] **S11.09** Mostrar indicador `CLOUD` antes y durante el job.
- [x] **S11.10** Añadir fake client sin llamadas facturables.
- [x] **S11.11** Pasar contract tests con el fake client.
- [x] **S11.12** Documentar privacidad y datos enviados.
- [x] **S11.13** Verificar que el provider nunca se activa implícitamente.

**Criterio de salida:** OpenAI es intercambiable, explícito y opcional; offline
sigue siendo el modo predeterminado.

## Sección 12 — ElevenLabs opcional

- [x] **S12.01** Diseñar configuración segura de API key.
- [x] **S12.02** Implementar adapter Scribe.
- [x] **S12.03** Mapear diarización al formato canónico.
- [x] **S12.04** Mapear word timestamps al formato canónico.
- [x] **S12.05** Implementar keyterms por proyecto sin contaminar dominio.
- [x] **S12.06** Manejar archivos largos y progreso.
- [x] **S12.07** Estimar coste antes de enviar.
- [x] **S12.08** Añadir fake client sin llamadas facturables.
- [x] **S12.09** Pasar contract tests con el fake client.
- [x] **S12.10** Documentar privacidad y datos enviados.
- [x] **S12.11** Verificar que UI/dominio central no cambian por este adapter.

**Criterio de salida:** ElevenLabs funciona como backend adicional sin convertirse
en dependencia del producto.

## Sección 13 — Calidad de transcripción

- [x] **S13.01** Modelar glossary/keyterms por proyecto.
- [x] **S13.02** Crear perfil académico explícito y reproducible.
- [x] **S13.03** Hacer VAD configurable por perfil.
- [x] **S13.04** Implementar heurísticas no destructivas contra alucinaciones.
- [x] **S13.05** Señalar segmentos de baja confianza.
- [x] **S13.06** Crear flujo de revisión de baja confianza.
- [x] **S13.07** Ejecutar comparación A/B de modelos sobre el mismo fixture.
- [x] **S13.08** Medir tiempo, realtime factor, RAM y VRAM.
- [x] **S13.09** Mantener dataset personal fuera de Git.
- [x] **S13.10** Añadir herramienta opcional de WER/CER.
- [x] **S13.11** Recomendar perfil por idioma usando resultados medidos.
- [x] **S13.12** Separar transcript literal de cualquier postprocesamiento.

**Criterio de salida:** el usuario puede medir qué configuración funciona mejor
con sus grabaciones sin presentar intuiciones como resultados.

## Sección 14 — Robustez

- [x] **S14.01** Recuperar jobs interrumpidos al iniciar.
- [x] **S14.02** Escribir checkpoints y metadatos críticos atómicamente.
- [x] **S14.03** Comprobar espacio antes de import/normalización.
- [x] **S14.04** Comprobar espacio antes de descargar modelos.
- [x] **S14.05** Añadir guard de RAM.
- [x] **S14.06** Añadir guard de VRAM.
- [x] **S14.07** Liberar modelos entre ASR y diarización por defecto.
- [x] **S14.08** Implementar cancelación real por cada etapa procesable.
- [x] **S14.09** Recuperar descargas corruptas/incompletas.
- [x] **S14.10** Crear backup antes de una migración destructiva.
- [x] **S14.11** Generar bundle diagnóstico redactado.
- [x] **S14.12** Añadir fuzz tests de metadata de importación.
- [x] **S14.13** Probar cierre/reapertura durante un job largo.
- [x] **S14.14** Probar idempotencia de resume.
- [x] **S14.15** Renombrar proyecto `PATCH /api/projects/{id}` (`tests/integration/test_library_projects_api.py`).
- [x] **S14.16** Eliminar proyecto con sus medios y 409 `project_busy` (`tests/integration/test_library_projects_api.py`).

**Criterio de salida:** cerrar o reabrir VOZ no destruye el trabajo confirmado y
los fallos dan acciones recuperables.

## Sección 15 — Packaging y release

- [x] **S15.01** Construir wheel reproducible.
- [x] **S15.02** Construir sdist reproducible.
- [x] **S15.03** Verificar instalación con `uv tool install`.
- [x] **S15.04** Incluir el bundle frontend en el paquete.
- [x] **S15.05** Verificar ejecución sin checkout de desarrollo.
- [x] **S15.06** Crear workflow de release privado/de prueba.
- [x] **S15.07** Generar checksums de artefactos.
- [x] **S15.08** Mantener changelog.
- [x] **S15.09** Adoptar versionado semántico.
- [x] **S15.10** Verificar instalación documentada en Bazzite.
- [x] **S15.11** Documentar instalación Linux genérica.
- [x] **S15.12** Evaluar AppImage con prototipo medido.
- [x] **S15.13** Evaluar Flatpak con prototipo medido.
- [ ] **S15.14** Publicar una release solo con autorización explícita.
- [x] **S15.15** Portable en Windows/macOS/Linux con doble clic y FFmpeg bajo demanda (job `backend-portable` de `.github/workflows/ci.yml` en windows-latest y macos-latest; sin prueba manual).
- [x] **S15.16** Un segundo doble clic reutiliza el VOZ abierto (`tests/unit/test_cli.py`).
- [ ] **S15.17** PWA instalable desde Chrome/Edge (sin test automatizado).
- [x] **S15.18** Acceso directo de escritorio (`tests/unit/infrastructure/test_desktop_shortcut.py`, `tests/integration/test_desktop_shortcut_api.py`; no portable: ver Programa V V1-05).

**Criterio de salida:** un tercero puede instalar un artefacto siguiendo solo el
README, sin depender del checkout.

## Sección 16 — Open source readiness

- [x] **S16.01** Crear README profesional y honesto sobre el estado actual.
- [x] **S16.02** Añadir demo y capturas correspondientes a funciones reales.
- [x] **S16.03** Crear `CONTRIBUTING.md`.
- [x] **S16.04** Crear `CODE_OF_CONDUCT.md`.
- [x] **S16.05** Crear `SECURITY.md` con canal de reporte.
- [x] **S16.06** Crear issue template de bug.
- [x] **S16.07** Crear issue template de feature.
- [x] **S16.08** Crear PR template con checks relevantes.
- [x] **S16.09** Documentar diagrama C4 de contexto.
- [x] **S16.10** Documentar diagrama C4 de contenedores.
- [x] **S16.11** Documentar diagrama C4 de componentes.
- [x] **S16.12** Completar ADR de límites hexagonales.
- [x] **S16.13** Completar ADR de SQLite/filesystem.
- [x] **S16.14** Completar ADR de ingestión FFmpeg.
- [x] **S16.15** Completar ADR de providers.
- [x] **S16.16** Completar ADR local-first.
- [x] **S16.17** Documentar licencias de todos los fixtures.
- [x] **S16.18** Crear `NOTICE` para código/dependencias reutilizadas.
- [x] **S16.19** Auditar secretos y archivos ignorados antes de abrir el repo.
- [ ] **S16.20** Hacer público el repositorio solo con autorización explícita.

**Criterio de salida:** el repositorio está listo para recibir contribuciones
externas, con evidencias reales y sin material privado.

---

## Hitos

- **Skeleton ejecutable:** Sección 1 completa.
- **MVP local:** Secciones 1–6 y 10 completas.
- **Providers extensibles demostrados:** Secciones 9, 11 o 12 según prioridad,
  manteniendo al menos dos implementations bajo contract tests.
- **Release instalable:** Sección 15 completa.
- **Apertura pública:** Sección 16 completa y autorización explícita del dueño.

Los hitos no sustituyen los checkboxes: se declaran alcanzados solo cuando todos
sus IDs obligatorios están verificados.
