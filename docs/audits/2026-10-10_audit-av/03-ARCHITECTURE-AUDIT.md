# 03 · Auditoría de arquitectura

## Veredicto

La arquitectura real coincide con la prevista (`AGENTS.md` y ADR-0001): un monolito modular con puertos y adaptadores. La dirección de dependencias se cumple, no hay ciclos y el composition root es el único sitio donde se instancian adaptadores. Los problemas son de **duplicación local**, **observabilidad** y **un fallo silencioso** en el worker, no de diseño de fondo. No se recomienda reescribir nada.

## Comprobaciones verificadas

### Dependencias entre módulos — verificado con script AST

Script: `evidencia/import_graph.py`, ejecutado con `.venv/bin/python -I` sobre `src/voz`.

| Métrica | Resultado |
|---|---|
| Módulos analizados | 160 |
| Aristas internas | 488 |
| Violaciones `domain → no-domain` | **0** |
| Violaciones `application → infrastructure/interfaces` | **0** |
| Ciclos | **0** |

Limitación: el script resuelve imports relativos y absolutos por nombre de módulo; no ejecuta el código. Es suficiente para capas y ciclos a nivel de módulo.

### Imports de frameworks en el dominio

`grep -rn 'fastapi\|sqlalchemy\|faster_whisper\|sherpa\|ffmpeg' src/voz/domain` no devuelve imports reales (verificado con la misma comprobación del script: cero aristas hacia fuera de `domain`).

### Composition root

- `src/voz/bootstrap.py:238` `create_app(...)` instancia repositorios SQLite, almacenamiento, probes de FFmpeg, catálogos, runner de modelos, proveedores cloud y routers. Es el único lugar de wiring (≈360 líneas de cableado).
- `bootstrap.py:596` `__getattr__("app")` crea la app de forma perezosa para que `uvicorn voz.bootstrap:app` no abra la base de datos al importar. Funciona, pero es un truco; documentar.
- `bootstrap.py` tiene 601 líneas. Es grande pero coherente con su rol; dividir por contexto (modelos, proveedores, jobs) solo si crece.

### Concurrencia

- **Un único worker daemon** para jobs: `application/job_runner.py:193-234` (`threading.Thread(target=self._loop, daemon=True)`), cola `queue.Queue` FIFO. Concurrencia de jobs = 1, deliberado (`# ponytail: un worker global; N workers cuando importe`, línea 196).
- Estado compartido protegido: `_LockedJobs` y `_LockedCheckpoints` (líneas 150–190) envuelven repositorios con `threading.Lock`.
- Cancelación con `threading.Event` (`_cancel`, `_stopping`). `run_job` hace `_cancel.clear()` al empezar cada job (línea ~305); con un solo worker no hay carrera.
- SSE: sondeo en hilo (`interfaces/api/job_events.py`), keep-alive y evento `end` terminal.
- Diarización: subproceso hijo (`infrastructure/diarization/sherpa.py:205`, `worker.py`), motivo documentado en `worker.py:1-10`: sherpa-onnx retiene el GIL durante minutos.
- FFmpeg: `subprocess.Popen` con pipes, parada ordenada en `ffmpeg.py:359-375`.

### Estado global

| Ubicación | Qué es | Riesgo |
|---|---|---|
| `infrastructure/asr/faster_whisper.py:97` `_dll_directory_handles: list[object]` | Lista módulo-global que mantiene vivos los handles de `os.add_dll_directory` en Windows | Bajo; está comentado |
| `application/job_runner.py` `_queued`, `_current` | Estado del runner, protegido por lock | Bajo |
| Constantes `frozenset` en varios módulos | Inmutables | Ninguno |

### Patrones aplicados

- Puertos como `Protocol` estructurales (`application/ports/*.py`), p. ej. `TranscriptionProvider`, `DiarizationProvider`, `TranscriptExporter`, `MediaProbe`.
- Adaptadores detrás de puertos: `FasterWhisperProvider`, `WhisperCppProvider`, `OpenAITranscription`, `ElevenLabsScribe`, `SherpaOnnxDiarizationProvider` (con `FakeOpenAITransport` para tests).
- Registro de proveedores (`application/transcription_provider_registry.py`) con rechazo de duplicados y contratos incompletos (ASR-REGISTRY-001).
- Contratos comunes verificados por una suite de contrato (`tests/contract/test_transcription_provider.py`).
- Entidades inmutables con invariantes (`domain/entities/*.py`), transiciones de estado explícitas en `TranscriptionJob`.

### Errores

- Contrato de error uniforme `{"detail": {"code", "message"}}`, cumplido en los routers revisados (`_error(...)` en 7 módulos).
- Errores tipados en aplicación: `JobNotFound`, `JobTerminal`, `MediaNormalizationError`, etc.
- Excepciones amplias: **19 `except Exception`** y **6 `except BaseException`**. Los 4 `BaseException` revisados (`safe_fs.py:214`, `media_storage.py:384`, `import_media.py:92`, `ffmpeg.py:287`) limpian y **re-lanzan**: correcto. Los `except Exception` de `job_runner.py` (líneas 319, 460, 502, 524, 547) requieren revisión; el de la línea 319 no registra nada (AV-P1-03).

### Observabilidad

- `logging` aparece en solo **4 archivos** de `src/voz`.
- Salida por `print(..., file=sys.stderr)` en `infrastructure/audio/ffmpeg_tools.py:105` y en el worker de diarización (protocolo por stdout, deliberado).
- Hay diagnóstico (`voz doctor`, bundle redactado `diagnostics_bundle.py`) y progreso por SSE, pero **no hay log estructurado ni archivo de log rotado**. Para una app local es aceptable; para depurar fallos de worker no lo es.

## Duplicación y componentes grandes — verificado

| Duplicado | Ubicaciones | Recomendación |
|---|---|---|
| `_error(status, code, message)` | `interfaces/api/`: `desktop_shortcut.py:17`, `providers.py:133`, `segments.py:66`, `jobs.py:97`, `speakers.py:55`, `media_stream.py:78`, `media.py:134` | Un módulo `interfaces/api/errors.py` |
| `_UNSAFE_BIDI_CLASSES` | `infrastructure/media_storage.py:32` y `interfaces/api/media.py:39` | Una sola fuente, en dominio o en un módulo de utilidades de texto |
| Validadores de payload (`_text`, `_integer`, `_mapping`, `_object`, `_validate_uuid`, `_uuid`, `_require_uuid`, `_real`) | 2–7 copias cada uno, en distintos módulos de aplicación | Un módulo de validación compartido, sin cambiar firmas |

Componentes grandes (frontend): `SegmentList.tsx` 703 líneas, `ModelManager.tsx` 702, `SpeakersPanel.tsx` 509. No son problema hoy; son candidatos a dividir cuando se toquen.

## Dependencias y acoplamiento

- Backend: FastAPI, SQLAlchemy 2 y Alembic son el núcleo; faster-whisper y sherpa-onnx son extras opcionales. El núcleo arranca sin ellos (`GET /api/transcription-options` reporta el runtime como no disponible).
- `bootstrap.py` decide `diarization_runtime_available = find_spec("sherpa_onnx") is not None` (línea 282): la disponibilidad se detecta, no se importa. Correcto.
- Frontend: consume contratos de `apps/web/src/api/*.ts`; no conoce rutas del host ni esquema SQL. Cumple AGENTS.md.

## Complejidad innecesaria (candidatos a simplificar, no urgentes)

- Dos formas de representar una transición de job (`JobRunner._advance` y `_restart_stage`): revisar si se solapan.
- `ponytail:` marca **56 comentarios en `src`**, 2 en `tests`, 8 en `apps/web/src`: deuda deliberada, registrada aquí y en `11-TECHNICAL-DEBT.md`.

## Problemas de arquitectura detectados

1. Fallo silencioso del worker (AV-P1-03).
2. Duplicación de helpers API y validadores (AV-P2-03, AV-P2-04, AV-P2-05).
3. Observabilidad limitada (AV-P2-13).
4. Estado de la gobernanza: el plan Tauri existe como documento sin ADR, y `AGENTS.md:62` prohíbe Tauri sin ADR aceptado (AV-P2-14). No hay violación: nada está implementado.

## Lo que conviene conservar

- Puertos estructurales y suite de contrato común.
- Runner único con checkpoints y `recover()` al arranque.
- Diarización en subproceso y cancelación por evento.
- Separación de transporte falso para cloud.
- Composition root único.
