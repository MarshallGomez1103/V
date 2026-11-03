# 09 · Matriz de trazabilidad

HEAD `96284c5`. Una fila por hallazgo del Top 5 de cada informe (40 en total), con la severidad que asignó la investigación autora, sin cambios. La columna **Principio** es la clasificación de la revisión central. No se marca ninguna violación SOLID solo por el tamaño de un archivo. **Verif.** indica si la revisión central volvió a abrir la evidencia en el checkout (✔ = comprobada a mano; — = solo validado que la cita existe).

**STT RT**:
- **B**: bloquea el STT en tiempo real.
- **C**: lo condiciona.
- **—**: no influye.

| Hallazgo | Área | Principio | Evidencia principal | Severidad | STT RT | Verif. |
|---|---|---|---|---|---|---|
| DOMAIN-01 Sin modelo para sesión en vivo; parcial/final; identidad por índice | domain | Cohesión, encapsulamiento | `src/voz/domain/entities/transcription_job.py:129`; `src/voz/domain/entities/transcript.py:21`; `src/voz/application/job_runner.py:715` | alta | B | — |
| DOMAIN-02 `reopen_for_diarization` salta la tabla de transiciones; FAILED sin `error_code` | domain | Encapsulamiento (invariantes) | `src/voz/domain/entities/transcription_job.py:320-322` | alta | — | ✔ |
| DOMAIN-03 `display_name` no aplica `has_unsafe_filename_character` | domain | Encapsulamiento, seguridad | `src/voz/domain/entities/media_asset.py:54-57` | media | — | ✔ |
| DOMAIN-04 `Segment` admite combinaciones incoherentes (`edited`/`revision`/`original_text`) | domain | Encapsulamiento | `src/voz/domain/entities/segment.py:42-44` | media | C | — |
| DOMAIN-05 Vocabulario de proveedor en el dominio; `ModelCapability` mezcla hardware y capacidad | domain | Hexagonal, cohesión | ver `01_INFORME_DOMAIN.md` §8 | media | C | — |
| APPLICATION-01 La ejecución guardada en el snapshot no es la que recibe el proveedor | application | Fuente única de verdad, SRP | `src/voz/application/create_transcription_job.py:205-209`; `src/voz/bootstrap.py:295-312` | alta (impacto: hipótesis) | — | ✔ |
| APPLICATION-02 TTS cloud sin consentimiento por trabajo | application | Seguridad (fail-closed) | `src/voz/application/synthesis/create_synthesis_job.py` (sin `consent`); `create_transcription_job.py:170-175` | media | C | ✔ |
| APPLICATION-03 La API compatible crea un proyecto con audio por petición y no lo borra | application | Privacidad, retención | `src/voz/application/compatible_audio.py:224` | media | C | — |
| APPLICATION-04 La aplicación traduce errores a HTTP y lleva reglas de un motor | application | Hexagonal, OCP | `src/voz/application/ports/compatible_audio.py:47-53` | media | — | — |
| APPLICATION-05 Carrera TOCTOU al encolar descargas del mismo modelo | application | Concurrencia | `src/voz/application/model_tasks.py:222-268` | media | — | — |
| SPEECH-01 Sin streaming real: puerto batch, ningún motor incremental | speech | ISP/OCP (contrato), YAGNI respetado | `src/voz/application/ports/transcription.py:257-272` | alta | B | — |
| SPEECH-02 Diarización offline; necesita el audio completo | speech | Restricción de motor | `src/voz/infrastructure/diarization/sherpa.py:267-290` | alta | B (diarización en vivo) | — |
| SPEECH-03 whisper.cpp/FFmpeg sin plazo total; código ≠0 = «medio corrupto» | speech | Errores, recursos | `src/voz/infrastructure/asr/whisper_cpp.py:286-292`; `src/voz/infrastructure/audio/ffmpeg.py:280-281` | media | C | ✔ |
| SPEECH-04 Solape sin deduplicación textual; ventanas sherpa de 30 s sin solape | speech | Corrección | `src/voz/infrastructure/asr/sherpa_onnx_worker.py:149-161` | media | C | — |
| SPEECH-05 `release()` ignora `_busy`; borrar modelo no libera el runtime | speech | Concurrencia, recursos | `src/voz/infrastructure/asr/runtime_cache.py:53-57` | media | C | — |
| TTS_CLOUD-01 La clave guardada se envía al host nuevo al editar `base_url` | tts_cloud | Seguridad | `src/voz/interfaces/api/providers.py:182-185` | alta | — | ✔ |
| TTS_CLOUD-02 Endpoints de nube aceptan `http://` | tts_cloud | Seguridad | `src/voz/application/ports/compatible_endpoints.py:76-78` | alta | C | ✔ |
| TTS_CLOUD-03 Hijos heredan el entorno completo (claves) y cargan pesos sin límites | tts_cloud | Seguridad, mínimo privilegio | `src/voz/infrastructure/custom_model_worker.py:70-75`; `src/voz/infrastructure/tts/subprocess_provider.py:252-258` | alta | C | — |
| TTS_CLOUD-04 TTS en nube sin consentimiento por trabajo en el servidor | tts_cloud | Seguridad (fail-closed) | `src/voz/interfaces/api/synthesis.py:93-100` | media | C | ✔ (= APPLICATION-02) |
| TTS_CLOUD-05 Cancelación no corta la petición en vuelo (OpenAI, ElevenLabs); reanudación sin reconfirmar | tts_cloud | Concurrencia, consentimiento | `src/voz/infrastructure/cloud/openai_transcription.py:261`; `src/voz/application/job_runner.py:292-298` | media | C | — |
| persistence_jobs-01 Cancelar síntesis en PERSISTING deja audio de un job CANCELLED | persistence_jobs | Concurrencia, consistencia | `src/voz/application/synthesis/runner.py:294-302` | media (hipótesis) | — | — |
| persistence_jobs-02 CANCELLING no bloquea la admisión de otro job sobre el mismo medio | persistence_jobs | Invariante, concurrencia | `src/voz/domain/entities/transcription_job.py:40-51`; `src/voz/application/create_transcription_job.py:186-193` | media | — | ✔ |
| persistence_jobs-03 La síntesis acumula todo el PCM en memoria | persistence_jobs | Recursos, backpressure | `src/voz/application/synthesis/runner.py:269-285` | media | C | — |
| persistence_jobs-04 `stop()` con timeout puede dejar dos workers y el engine liberado | persistence_jobs | Concurrencia | `src/voz/application/job_runner.py:270-282` | media (hipótesis) | C | — |
| persistence_jobs-05 `kill_tree` en POSIX no mata nietos | persistence_jobs | Recursos | `src/voz/infrastructure/process_tree.py:21-33` | baja | C | ✔ |
| INTERFACES-01 Sin token, peticiones simples de origen cruzado llegan a rutas con efectos | interfaces | Seguridad | `src/voz/interfaces/api/server_auth.py:77-80` | media | C | — |
| INTERFACES-02 Lógica de negocio en routers (ETA, consentimiento, filtros, plazos) | interfaces | Hexagonal, SRP | `src/voz/interfaces/api/job_views.py:18-37`; `src/voz/interfaces/api/providers.py:177-180` | media | — | — |
| INTERFACES-03 Apagado bloqueable (uvicorn sin plazo; `join()` sin límite) | interfaces | Recursos | ver `06_INFORME_INTERFACES.md` §8 (parte en código de terceros) | media (hipótesis) | C | — |
| INTERFACES-04 WebSocket no operativo: sin librería WS en `uv.lock` ni rutas | interfaces | Restricción de transporte | `uv.lock` (uvicorn 0.52.4 sin `websockets`/`wsproto`) | media | B (si se elige WS) | ✔ |
| INTERFACES-05 Router acoplado a infraestructura; subprocesos sin plazo en el arranque | interfaces | Hexagonal, recursos | `src/voz/interfaces/api/media_stream.py:21` | baja | — | — |
| FRONTEND-01 Sin captura de micrófono ni detección de APIs | frontend | Capacidad ausente | `getUserMedia` sin coincidencias en `apps/web/src` | alta | B | ✔ |
| FRONTEND-02 Virtualización medida por índice; sin reinicio al filtrar | frontend | Corrección | `apps/web/src/components/SegmentList.tsx:316-350` | media | C | — |
| FRONTEND-03 Fallos de instantánea y de cancelación silenciados | frontend | Manejo de errores | `apps/web/src/hooks/useJobEvents.ts:46` | media | C | ✔ |
| FRONTEND-04 Subida sin cancelación; proyecto huérfano posible | frontend | UX, consistencia | `apps/web/src/components/NewProjectCard.tsx:130-155` | media | — | — |
| FRONTEND-05 Textos en español fijos llegan a la UI en inglés | frontend | i18n | `apps/web/src/api/jobEvents.ts:49` | media | — | ✔ |
| QUALITY-01 La CI no detecta dependencias vulnerables ni secretos | quality | Seguridad (cadena de suministro) | `.github/workflows/` sin auditoría | media | — | ✔ (además, en GitHub están desactivados secret scanning y Dependabot) |
| QUALITY-02 ruff, pyright, frontend y wheel solo en Ubuntu | quality | Calidad multiplataforma | `.github/workflows/ci.yml:37-42` | media | — | — |
| QUALITY-03 Pruebas con tiempo real y márgenes fijos; sin `pytest-timeout` | quality | Concurrencia (pruebas) | `tests/unit/test_asr_runtime_cache.py:128-141` | media | C | — |
| QUALITY-04 El bundle versionado no se compara con un build nuevo | quality | Integridad de artefactos | `apps/web/vite.config.ts:15`; `.github/workflows/ci.yml:101-102` | media | — | — |
| QUALITY-05 Skips silenciosos; `App.e2e.test.tsx` no es e2e; docs desfasadas | quality | Mantenibilidad | `tests/packaging/test_wheel_contents.py:24` | baja | — | — |

## Agregados

- Por severidad: alta 9 · media 28 · baja 3 (conteo sobre esta tabla).
- Las altas son de dos tipos:
  - seguridad: TTS_CLOUD-01, -02 y -03.
  - capacidad o modelo para STT en vivo: DOMAIN-01, SPEECH-01, SPEECH-02 y FRONTEND-01.

  A ellas se suman dos de consistencia interna: DOMAIN-02 y APPLICATION-01.
- Bloquean el STT en tiempo real (B): DOMAIN-01, SPEECH-01, SPEECH-02 (solo diarización en vivo), INTERFACES-04 (solo si se elige WebSocket) y FRONTEND-01.
- Repetidos en dos informes:
  - consentimiento TTS: APPLICATION-02 = TTS_CLOUD-04.
  - entorno heredado por hijos: TTS_CLOUD-03 ≈ `05` §4 (`constrained_process.py:167`).
  - `kill_tree`: persistence_jobs-05 ≈ `03` (sherpa ASR).
