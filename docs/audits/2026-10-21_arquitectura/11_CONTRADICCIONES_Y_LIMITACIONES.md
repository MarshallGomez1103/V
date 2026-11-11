# 11 · Contradicciones y limitaciones

HEAD `96284c5`. Este documento recoge las contradicciones entre informes, entre la documentación y el código, y entre lo reportado y lo observado. Recoge también los errores de cita detectados y los límites del proceso de auditoría. Al final incluye íntegra la segunda lectura de ADR y documentación.

## A. Lo reportado frente a lo observado

| Afirmación inicial | Observado | Clasificación |
|---|---|---|
| ~36 700 líneas Python de producción | 36 703 (`git ls-files 'src/voz/*.py'` + `wc -l`) | Observado, coincide |
| ~32 000 líneas TS/TSX | 31 986 en `apps/web/src` | Observado, coincide |
| 904 archivos versionados | 904 (`git ls-files`) | Observado, coincide |
| 12 ADR | 12 archivos en `docs/adr/`: **11 ADR numerados (0001–0011) + `README.md`** | Observado. La cifra cuenta el índice como ADR |
| 3131 pruebas backend | Conteo estático de 1838 funciones `def test_` en 223 archivos y 325 decoradores `@pytest.mark.parametrize`. La cifra expandida no se puede calcular sin recolectar las pruebas, y no aparece en el repo | Documentado por el propietario, **no comprobado** |
| 808 pruebas frontend | 76 archivos `*.test.ts(x)`. El recuento de llamadas `it(`/`test(` varía según el patrón: 668 (`07`), 684 (`08`) y 700 (revisión central). Hay 32 `.each` sin expandir | Documentado, **no comprobado** |
| CI verde | La API de GitHub (solo lectura) muestra los workflows CI y Launchers en `success` para `96284c5` (ejecuciones 39664028819 y 39664028894). Ver la limitación L3 | Observado fuera del checkout. Que un workflow pase no demuestra que la plataforma funcione en uso real |
| Consentimiento cloud explícito que falla cerrado | Se cumple en STT por trabajo y en el registro de endpoints. **No** se cumple en TTS en nube por trabajo, y al reanudar un trabajo no se vuelve a pedir (`02` APPLICATION-02, `04` TTS_CLOUD-04/05) | Observado. La afirmación general es **parcialmente falsa** |
| Jobs con progreso por SSE | SSE por sondeo de instantáneas cada 0,5 s, sin `id` ni `Last-Event-ID` (`src/voz/interfaces/api/job_events.py:32-34`, `:52-53`) | Observado. Matiz: no es un flujo de eventos con reanudación |

## B. Contradicciones entre informes (resueltas por la revisión central)

1. **`kill_tree` y los nietos.**
   - `05` dice que en POSIX solo mata al hijo directo. `08` cita `tests/unit/infrastructure/test_process_tree.py:18-28` como prueba del árbol de procesos.
   - Resolución tras leer el código: la prueba del nieto solo corre en Windows (`skipif(os.name != "nt", reason="POSIX ends trees by process group")`, `test_process_tree.py:27`). En POSIX, `kill_tree` llama a `child.kill()` (`src/voz/infrastructure/process_tree.py:32`).
   - Prevalece el hallazgo de `05`. El docstring («and its descendants», `process_tree.py:18`) solo es cierto si quien llama crea un grupo de procesos y lo mata aparte.
2. **Recuento de pruebas del frontend.** Tres cifras distintas (668/684/700) por diferencias de expresión regular. Ninguna es la de ejecución.
3. **Consentimiento TTS.** `02` y `04` llegan al mismo hallazgo por caminos distintos, y la revisión central lo comprobó: ni `src/voz/application/synthesis/` ni `src/voz/interfaces/api/synthesis.py` contienen la palabra `consent`. Ambos informes son consistentes; se cuenta una sola vez en la matriz.
4. **Entorno heredado por procesos hijos.**
   - `04` (TTS_CLOUD-03) cita `custom_model_worker.py` y `tts/subprocess_provider.py`.
   - `05` añade `src/voz/infrastructure/constrained_process.py:167`.
   - No se contradicen; se complementan.
5. **Ubicación del límite de recursos.** `04` cita `edge_lab_worker.py:63-70` como «application», pero el archivo es `src/voz/infrastructure/edge_lab_worker.py`. Es una errata de capa, no de contenido.

## C. Documentación frente a código

Resumen de la segunda lectura (texto completo en el anexo):
- **Docs de arquitectura desactualizadas.** `docs/architecture/01-contexto.md`, `02-contenedores.md` y `03-componentes.md` describen como «planned / no code» cosas que ya existen: proveedores cloud, whisper.cpp, diarización, Buzz, autenticación local, exportación HTTP, edición y API de instalación.
- **Índice de ADR incompleto.** `docs/architecture/README.md` no enlaza ADR-0010 ni ADR-0011.
- **ADR-0005.** Su disparador de revisión («dos proveedores reales») se cumplió sin que se registrara una revisión: hoy hay seis proveedores STT. Además afirma que los proveedores cloud y `DiarizationProvider` «no existen» (`docs/adr/0005-transcription-providers.md:69-76`). Un ADR es un registro histórico, así que el desfase del texto es esperable. Lo que queda abierto es la **revisión pendiente**, que condiciona S17.01.
- **ADR-0011** dice «planned» sobre un ejecutor que ya existe.
- **Rutas de `docs/api`.** Coinciden con las registradas en `src/voz/interfaces/api/`. Tres rutas solo se registran si se inyecta una dependencia, y la documentación no lo indica.
- **IDs internos.** `docs/api/*.md` conserva identificadores internos de planificación (`08` §3).

## D. Errores de cita detectados

Cada cita `ruta:línea` de los informes se validó automáticamente: el archivo debe estar versionado y la línea dentro de su rango.

| Informe | Válidas | Abreviadas, resolubles | Erróneas |
|---|---:|---:|---|
| 01 domain | 111 | 0 | 0 |
| 02 application | 119 | 20 | 0 |
| 03 speech | 130 | 2 | 0 |
| 04 tts_cloud | 148 | 16 | 1 elipsis (`apps/web/.../SpeakWorkspace.tsx` = `apps/web/src/components/SpeakWorkspace.tsx`) |
| 05 persistence_jobs | 94 | 6 | 1: `recoverable_transcription.py:459-483` no existe (el archivo tiene 317 líneas); el contenido citado está en `src/voz/application/job_runner.py:459-483` |
| 06 interfaces | 85 | 16 | 4 citas a código de terceros instalado localmente (`.venv/.../uvicorn/...`), no versionado ni verificable desde el checkout |
| 07 frontend | 122 | 0 | 0 |
| 08 quality | 95 | 1 | 0 |
| Segunda lectura ADR/docs | 84 | 1 | 0 |

Validar no es comprobar el contenido. La revisión central abrió a mano 15 evidencias clave (marcadas ✔ en `09`) y todas respaldan el hallazgo. El resto de citas solo se comprobó en cuanto a existencia.

## E. Limitaciones del proceso

- **L1 · Nada se ejecutó.** Ni pruebas, ni builds, ni servidores, ni migraciones. Todo comportamiento en tiempo de ejecución (carreras, bloqueos de apagado, consumo de memoria, latencia) es **hipótesis** mientras no se reproduzca.
- **L2 · Ejecución.** Las ocho revisiones de la primera pasada se hicieron **en paralelo**, y la segunda lectura (`informe_adr_docs`) después.
- **L2b · Entrega de los informes.** Cuatro informes (`04`, `05`, `07` y `08`) se guardaron copiando literalmente el texto final de cada revisión, sin editarlo. `01`, `02`, `03` y `06` se redactaron directamente.
- **L3 · Excepción a la regla de no usar la red.** La revisión central consultó la API de GitHub (lectura, dos llamadas) para el estado de CI de `96284c5`. Ninguna investigación accedió a la red.
- **L4 · Fuera del repositorio.** `informe_interfaces` leyó el código de uvicorn instalado en el entorno virtual local para explicar el rechazo de WebSocket. Es evidencia de terceros, y la versión coincide con `uv.lock` (0.52.4).
- **L5 · Cobertura.** De 904 archivos:
  - 184 con lectura profunda;
  - 552 superficial;
  - 30 en segunda lectura (ADR y docs);
  - 59 de contexto de la revisión central;
  - 79 omitidos: 43 SCSS y 11 catálogos i18n tipados (frontend, sin lógica), 22 binarios, iconos y textos de licencia (quality), y `alembic.ini` y `migrations/script.py.mako` (persistence).

  No se auditó el 100 % del código: 552 archivos se revisaron solo por cabecera, imports y definiciones.
- **L6 · Severidades.** Las fija cada investigación y la revisión central no las modifica. Varias altas dependen de un impacto marcado como hipótesis (p. ej. APPLICATION-01).
- **L7 · Datos sensibles.** No se leyeron secretos ni audio. Los informes citan rutas de código, no valores. **Los hallazgos de seguridad (TTS_CLOUD-01/02/03, INTERFACES-01) describen debilidades de un repositorio público. Conviene compartir este paquete de forma privada y no publicarlo hasta corregirlas.**

---

## Anexo · Segunda lectura de ADR y documentación (`informe_adr_docs`, texto íntegro)

### INFORME — adr_docs (segunda lectura)

**Metadatos:** 2026-10-21 · HEAD 96284c5 · rutas en el repo, relativas. Alcance: Decision y Status de los ADR 0001–0011; docs/architecture completo por grep de afirmaciones; docs/api por rutas y parámetros (grep), no prosa completa.
**Cobertura:** asignados 27 docs (ADR 11 + architecture 3 + api 13) · profunda: ADR Decision · superficial: Context, Consequences, docs/api prosa · omitidos: README de los tres directorios solo por índice.

#### 1. Tabla ADR

| ADR | Decisión | Estado | ¿Cumple el código? | Evidencia |
|---|---|---|---|---|
| 0001 | Monolito modular local, hexagonal; SSE antes que WebSocket | Accepted | Sí (estático) | 0 imports de fastapi/sqlalchemy/faster_whisper/typer en `src/voz/application` y `src/voz/domain`; puertos en `src/voz/application/ports/`; composición `src/voz/bootstrap.py:295` |
| 0002 | SQLite + SQLAlchemy 2, Alembic, WAL, busy 5 s, XDG, `voz.sqlite3` | Accepted | Sí | `src/voz/infrastructure/persistence/database.py:11,48`; `src/voz/bootstrap.py:229,692` |
| 0003 | Ingesta FFmpeg sobre originales inmutables; sin derivado parcial | Accepted | Parcial (no auditado) | `src/voz/infrastructure/audio/ffmpeg.py` y `ffprobe.py` existen; invariantes no revisadas |
| 0004 | Faster Whisper local (`local_files_only`), SHA de revisión, chunks recuperables | Accepted | Sí en lo citado | `src/voz/infrastructure/asr/faster_whisper.py:246,260,475`; clase en `:265`; SHA-40 y manifiesto no verificados |
| 0005 | Puerto Protocol único; registro en mapa; sin plugins hasta dos proveedores reales | Accepted | Estructura sí; **disparador de revisión incumplido** (proceso) | `src/voz/application/transcription_provider_registry.py:34`; sin `entry_points` en `src/voz`. Ya hay 6 proveedores: `asr/faster_whisper.py:265`, `asr/whisper_cpp.py:154`, `asr/sherpa_onnx.py:66`, `cloud/openai_transcription.py:87`, `cloud/elevenlabs_scribe.py:142`, `cloud/openai_compatible.py:170` |
| 0006 | Local-first, loopback 127.0.0.1:8765, sin nube implícita, sin telemetría | Accepted | Sí (telemetría no verificada) | `src/voz/interfaces/cli/main.py:37-38`; `src/voz/interfaces/api/server_auth.py:58`; `src/voz/application/create_transcription_job.py:170`; `src/voz/interfaces/api/providers.py:177` |
| 0007 | sherpa-onnx para diarización, sin torch; modelos fijados; umbral 0.3 | Accepted | Sí en lo citado | `src/voz/application/ports/diarization.py:131`; `src/voz/infrastructure/diarization/sherpa.py:293`; umbral `sherpa.py:44`; SHA-256 e instalación no verificados |
| 0008 | Word timestamps nativos de Faster Whisper, sin WhisperX | Accepted | Sí | `src/voz/infrastructure/asr/faster_whisper.py:356,364`; `src/voz/application/ports/transcription.py:99,219`; `src/voz/application/job_runner.py:783` |
| 0009 | Renombre a V; CLI `v` con alias `voz`; paquete `voz` intacto | Accepted | Sí | `pyproject.toml:50-52`; `src/voz/` sin renombrar |
| 0010 | Engine/modelo; port TTS; ComputeSlot único; OpenAI-compatible cliente y servidor | Accepted | Sí (parcial) | `src/voz/application/ports/speech_synthesis.py:152`; `src/voz/application/compute_slot.py:28-34,53`; `src/voz/bootstrap.py:364`; `src/voz/application/job_runner.py:350`; `src/voz/application/synthesis/runner.py:180`; `src/voz/interfaces/api/openai_compat.py:438-440`. Diarización dentro del slot: no verificado (`DIARIZATION` existe en el enum, no lo hallé en job_runner) |
| 0011 | Edge Lab: límites de recursos, árbol de procesos, controles explícitos | Accepted (2026-10-15) | Inconsistente con su texto | `docs/adr/0011-edge-lab.md:7` dice ejecutor y formato "planned", pero existen `src/voz/application/edge_lab.py`, `src/voz/infrastructure/edge_lab_worker.py`, `src/voz/infrastructure/constrained_process.py`, `src/voz/interfaces/cli/lab.py` |

#### 2. Documentación desactualizada o contradictoria

1. `docs/adr/0005-transcription-providers.md:75` "Cloud providers ... do not exist in the code" vs `src/voz/infrastructure/cloud/openai_transcription.py:87` y `cloud/elevenlabs_scribe.py:142`.
2. `docs/adr/0005-transcription-providers.md:69-71` "DiarizationProvider and AlignmentProvider ... do not exist" vs `src/voz/application/ports/diarization.py:131` (Protocol con implementación en `sherpa.py:293`); `ports/alignment.py:24` existe sin implementación (coherente con ADR-0008 §9).
3. `docs/adr/0005-transcription-providers.md:62-67`: el disparador "dos proveedores reales" ya se cumplió (fila 0005) sin ADR nueva ni revisión registrada. Desfase de proceso, no de código.
4. `docs/architecture/01-contexto.md:24-27` y `:60-68` (sección "Planned (not in the code)"): nube "planned" vs `cloud/` (punto 1); whisper.cpp "planned" vs `src/voz/infrastructure/asr/whisper_cpp.py:154`; pyannote "planned" vs ADR-0007 y `sherpa.py:293`; Buzz "there is no code" (`:68`) vs `src/voz/infrastructure/buzz_cache.py`, cableado en `src/voz/bootstrap.py:113,405`.
5. `docs/architecture/02-contenedores.md:100-105`: contenedor de nube, whisper.cpp y diarización "no code" (`:101`), y "local authentication is still planned" (`:105`) vs `src/voz/interfaces/api/server_auth.py:58` (ServerAuthMiddleware), `src/voz/bootstrap.py:221,727` y `docs/api/authentication.md` (implementada, opcional).
6. `docs/architecture/02-contenedores.md:77`: el SSE emite `job` "when state, progress or updated_at change" vs `src/voz/interfaces/api/job_events.py:37-45` (huella de 5 campos: state, progress, stage_progress, stage_started_at, updated_at). `docs/api/jobs.md:274-276` sí coincide con el código.
7. `docs/architecture/03-componentes.md:281-285` "Planned (no code)": "DiarizationProvider" existe (`ports/diarization.py:131`); "wired HTTP export" está cableado (`src/voz/bootstrap.py:204,858`; `src/voz/interfaces/api/export.py:59`); "transcript editing" está cableado (`src/voz/interfaces/api/segments.py:94`; `src/voz/bootstrap.py:784`); "installation API/CLI": la API existe (`src/voz/interfaces/api/model_tasks.py:88`), la CLI no hallada en `src/voz/interfaces/cli/main.py`.
8. `docs/architecture/03-componentes.md:159`: "the HTTP export wiring ... was not in bootstrap.py when this was written" está obsoleto: `src/voz/bootstrap.py:858` lo incluye.
9. `docs/architecture/README.md:42-50`: el índice de ADR llega solo a 0009 (faltan 0010 y 0011). Omisión (hipótesis de intención no confirmada).
10. `docs/adr/README.md` (fila 0009) da el título "…(`v` + `voz` alias, internals unchanged)"; `docs/adr/0009-rename-to-v.md:1` dice "…with backward compatibility". Menor.
11. `docs/api/providers.md:45,82`, `docs/api/jobs.md:450` y `docs/api/projects.md:16-17` documentan rutas que el código registra solo si hay dependencia inyectada (`src/voz/interfaces/api/providers.py:350`, `jobs.py:376`, `projects.py:216`). La doc no lo indica. Si el arranque normal las monta: no verificado.
- Rutas de docs/api (resto): coinciden con `add_api_route` y `@router` de `src/voz/interfaces/api/`. Parámetros comprobados: `confirm`, `after_ms`, `download`, `buckets`, `limit`, `timestamps`, `group_by_speaker`, `media_asset_id`, `language`, `project_id`.

#### 3. Restricciones para STT en tiempo real

- **Puerto (ADR-0005 §1, §6, §7; `docs/adr/0005-transcription-providers.md:30-37,62-71`):** `TranscriptionProvider.transcribe(audio: BinaryIO, ...)` es contrato de archivo completo, sin flujo. Un puerto de streaming debe ser contrato aparte (§7), y §6 exige revisar ADR-0005 antes; esa revisión está pendiente.
- **Local-first y consentimiento (ADR-0006 §1, §3; `docs/adr/0006-local-first-privacy.md:27,37`):** local por defecto; nube solo con selección explícita, aviso y consentimiento (`src/voz/application/create_transcription_job.py:170`); endpoints compatibles con consentimiento guardado (`src/voz/interfaces/api/providers.py:177`); sin fallback silencioso local→nube. ROADMAP §17 (`ROADMAP.md:608-612`) pide el mismo principio.
- **Red (ADR-0006 §2; ADR-0010 §5):** 127.0.0.1:8765 por defecto. La captura de audio en vivo desde el navegador es tráfico nuevo; fuera de loopback exige token (`src/voz/interfaces/api/server_auth.py:79-85` ya contempla scope websocket; `src/voz/interfaces/api/host_guard.py:52-60`).
- **Transporte (ADR-0001 `docs/adr/0001-modular-monolith.md:71-73`):** SSE para progreso servidor→navegador; WebSocket solo ante una necesidad bidireccional concreta. La captura de audio en vivo parece esa necesidad (hipótesis); no hay decisión registrada.
- **SQLite y jobs (ADR-0002 y ADR-0004, Decision):** persistencia por operación; chunks recuperables con checkpoint en una transacción (`src/voz/infrastructure/persistence/transcription_checkpoints.py:186`); `busy_timeout` 5 s (`database.py:11`). El modelo es batch; la política de durabilidad del texto parcial no está decidida (hipótesis: escrituras frecuentes podrían competir con jobs).
- **Slot de cómputo (ADR-0010 §4; `src/voz/application/compute_slot.py:53`; `src/voz/application/job_runner.py:349-350`):** una inferencia pesada a la vez; el STT en vivo competiría con lotes en cola. Prioridad o exclusión no decidida. `SingleRuntimeCache` (`src/voz/infrastructure/asr/runtime_cache.py:13`) mantiene un runtime residente.
- **Motores (ADR-0004:41; ADR-0010 §1):** motores son módulos del repo, registrados en bootstrap; nunca código descargado; un solo engine activo. Un motor de streaming sería adaptador nuevo.
- **Originales inmutables (ADR-0003:73,108):** no se publica derivado parcial; el audio en vivo aún no tiene original. Decisión abierta (hipótesis).
- **Capacidad prevista:** `src/voz/domain/entities/model_descriptor.py:35` (`REALTIME`); `docs/api/models.md:133` "none yet". Sin motor.
- **Coste (ADR-0008 §2; `ports/transcription.py:219`):** `word_timestamps=True` por defecto; medir latencia antes de usarlo en vivo (hipótesis).

**Preguntas finales**
- ¿Qué ADR condicionan el STT en tiempo real? 0001 (transporte), 0002 (SQLite), 0004 (chunks batch, un engine), 0005 (puerto por archivo, revisión vencida), 0006 (local-first y consentimiento), 0010 (ComputeSlot, modelos sin código remoto); 0003 (originales) y 0008 (word timestamps) de forma indirecta. Ninguno trata streaming.
- ¿Qué transporte o streaming ya está registrado? Solo SSE para snapshots de estado del job (`src/voz/interfaces/api/job_events.py:52-53`: sondeo 0,5 s y keepalive 15 s; `docs/api/jobs.md:271-276`), y el preview por checkpoints `GET /api/jobs/{id}/preview?after_ms=` (`src/voz/interfaces/api/jobs.py:322`; `docs/api/jobs.md:130`), que sondea segmentos ya confirmados. Ningún ADR fija transporte de audio ni de texto parcial; S17.01 sigue abierto (`ROADMAP.md:614`).

#### 4. No verificado
- Nada se ejecutó: ni tests, ni app, ni instalación. Ausencia de telemetría (ADR-0006 §5) y de fuentes de terceros en el web solo con grep acotado.
- ADR-0004 (SHA-40, manifiesto), ADR-0007 (SHA-256, instalación), ADR-0003 (invariantes de ingesta), ADR-0011 (límites de recursos y controles).
- Diarización dentro del ComputeSlot (ADR-0010 §4).
- docs/api: no comparé códigos de error ni cuerpos de respuesta; README de cada directorio solo por índice.
- Context y Consequences de los ADR no leídos completos.
- Los entregables A/B del BRIEF no se escribieron: la invocación pedía solo el mensaje final.
