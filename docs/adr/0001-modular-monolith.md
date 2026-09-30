# ADR-0001: Monolito modular local con arquitectura hexagonal

- Estado: Aceptada
- Fecha: 2026-09-01
- Responsables: mantenedores de VOZ
- Alcance: arquitectura inicial del producto y límites hexagonales
- Última revisión: 2026-09-30 (S16.12, sin cambio de decisión)
- Diagramas: [C4 contexto](../architecture/01-contexto.md),
  [contenedores](../architecture/02-contenedores.md),
  [componentes](../architecture/03-componentes.md)

## Contexto

VOZ será una aplicación local-first para importar audio o video, ejecutar
transcripciones largas, editar resultados sincronizados y exportarlos. En una
misma máquina compartirá GPU, filesystem, base de datos y ciclo de vida. La
primera versión necesita una instalación sencilla, funcionamiento sin Internet
después de descargar modelos y capacidad de incorporar distintos proveedores de
transcripción y diarización.

El trabajo pesado debe ejecutarse sin bloquear la interfaz y debe poder guardar
progreso recuperable. Sin embargo, separar la aplicación en servicios
independientes desde el inicio agregaría puertos, despliegues, serialización,
observabilidad distribuida y nuevos modos de fallo sin aislar recursos físicos:
todos seguirían compitiendo por la misma GPU y el mismo disco.

La variación que sí conviene aislar está entre el dominio y los mecanismos
externos: FastAPI, SQLite, FFmpeg, motores ASR, proveedores cloud y la interfaz
web.

## Decisión

VOZ se implementará inicialmente como un **monolito modular local** con
**arquitectura Clean/Hexagonal** y un **pipeline interno asíncrono de jobs**.

Las dependencias apuntan hacia el núcleo:

```text
Web UI / CLI / API
        |
        v
Application use cases
        |
        v
Domain

Infrastructure adapters implement application/domain ports
```

Se establecen estas fronteras:

- **Domain:** entidades, value objects, reglas e invariantes sin dependencias de
  frameworks.
- **Application:** casos de uso, puertos y coordinación del pipeline.
- **Infrastructure:** adaptadores de persistencia, filesystem, FFmpeg, modelos,
  ASR, diarización y observabilidad.
- **Interfaces:** API HTTP, CLI y traducción entre contratos externos e internos.
- **Web UI:** cliente del contrato HTTP/eventos; no conoce rutas del host ni
  detalles de proveedor.

Los proveedores externos implementarán contratos comunes, por ejemplo
`TranscriptionProvider`, `DiarizationProvider` y `AlignmentProvider` (hoy solo
existe el primero; ver la revisión más abajo). La selección y construcción de
adaptadores ocurre en un composition root.

Las operaciones largas se modelarán como jobs con estado explícito, progreso,
cancelación, errores tipados y checkpoints cuando corresponda. Para progreso de
servidor a navegador se preferirá SSE; WebSocket solo se añadirá si aparece una
necesidad bidireccional concreta.

SQLite y el filesystem son decisiones iniciales de infraestructura, no
dependencias del dominio. Los datos de ejecución respetarán XDG Base Directory y
se mantendrán fuera del checkout.

## Consecuencias positivas

- Una instalación y un proceso local son suficientes para la primera versión.
- El dominio se puede probar sin cargar GPU, FFmpeg, FastAPI o clientes cloud.
- Cambiar Faster Whisper por whisper.cpp no requiere modificar el dominio.
- Añadir un proveedor cloud no obliga a rediseñar la representación canónica del
  transcript ni la UI central.
- La persistencia y los providers pueden evolucionar mediante puertos y
  adaptadores.
- Se conservan checkpoints y eventos de progreso sin introducir infraestructura
  distribuida.
- El despliegue local, el diagnóstico y la privacidad son más comprensibles.

## Costes y límites

- Las fronteras modulares dependen de disciplina y pruebas; no las impone una
  frontera de proceso.
- Una tarea que bloquee el event loop puede afectar toda la aplicación. El
  trabajo de CPU/GPU debe ejecutarse mediante workers/procesos apropiados.
- Un fallo del proceso puede interrumpir todos los módulos, por lo que la
  persistencia incremental y la recuperación son requisitos reales.
- SQLite no pretende cubrir uso multiusuario distribuido.
- El composition root debe evitar acoplar casos de uso a implementaciones
  concretas.

## Alternativas consideradas

### Microservicios desde v1

Rechazada. Multiplica despliegue, comunicación, observabilidad y recuperación,
pero no separa la GPU ni mejora el caso de un usuario local.

### Integración directa con el proceso o GUI de Buzz

Rechazada como arquitectura central. Buzz puede ser referencia y su cache puede
integrarse mediante un adaptador opcional, pero sus detalles internos no serán
el contrato de VOZ.

### Aplicación de escritorio Electron/Tauri desde el inicio

Pospuesta. Primero se validará el flujo web local servido por `voz`. Un wrapper
de escritorio puede evaluarse después sin cambiar el núcleo.

### Event Sourcing o CQRS completo

Rechazados para v1. Comandos y consultas separados a nivel de casos de uso,
junto con checkpoints de jobs, cubren las necesidades conocidas con menor
complejidad.

### Capas sin ports (application llama a SQLAlchemy y FFmpeg directamente)

Rechazada. Habría eliminado el código de adaptación, pero los tests de casos de
uso necesitarían base de datos, binarios y modelos reales, y cambiar un
proveedor tocaría la lógica de negocio.

### Herramienta de arquitectura (import-linter u otra) desde el inicio

Pospuesta. Añadiría una dependencia de desarrollo; el test de AST existente
cubre el caso más importante. Se reevaluará al documentar la guarda planificada
(regla de dependencias de [AGENTS.md](../../AGENTS.md)).

## Límites hexagonales: reglas y evidencia actual (revisión 2026-09-30)

Mapa de capas a código real:

| Capa | Directorio | Puede importar |
| --- | --- | --- |
| Domain | `src/voz/domain/` | solo biblioteca estándar y su propio paquete |
| Application (casos de uso y ports) | `src/voz/application/`, `src/voz/application/ports/` | domain y biblioteca estándar |
| Infrastructure (adapters de salida) | `src/voz/infrastructure/` | application (ports), domain y SDKs concretos |
| Interfaces (adapters de entrada) | `src/voz/interfaces/` | application, domain y frameworks de transporte |
| Composition root | `src/voz/bootstrap.py` | todas las capas; único lugar que cablea adapters |

Evidencia por regla (la columna «Automatizado» distingue un test que falla si la
regla se rompe de una comprobación puntual hecha al revisar):

| Regla | Evidencia | Automatizado |
| --- | --- | --- |
| `domain` no importa frameworks | `tests/unit/domain/test_entity_invariants.py::test_domain_does_not_import_framework_or_persistence_packages` recorre el AST y veta `fastapi`, `pydantic` y `sqlalchemy`. Una búsqueda por `grep` el 2026-09-30 no halló imports de `torch`, `faster_whisper`, `typer`, `uvicorn` ni `voz.application` en `src/voz/domain`. | Parcial: la lista vetada es corta. |
| `application` no importa adapters ni frameworks | `grep` del 2026-09-30 sin resultados para `fastapi`, `sqlalchemy`, `starlette`, `faster_whisper`, `typer`, `uvicorn`, `voz.infrastructure` y `voz.interfaces` en `src/voz/application`. El test `tests/unit/application/test_transcription_provider_registry.py::test_registry_has_no_domain_infrastructure_or_framework_imports` fija la lista de imports de un módulo. | Parcial: un solo módulo. |
| Casos de uso dependen de ports | `ImportMedia`, `NormalizeImportedMedia`, `PrepareInferenceAudio`, `CreateTranscriptionJob`, `JobRunner` y `RecoverableTranscription` reciben `MediaStoragePort`, `MediaProbePort`, `MediaNormalizationPort`, repositories, `TranscriptionCheckpointStore` y `TranscriptionProvider` como campos o parámetros. Tests unitarios de application usan dobles en memoria (`tests/unit/application/`). | Sí, indirectamente: los tests no necesitan SQL, FFmpeg ni ASR. |
| Los ports no filtran detalles de infraestructura | `src/voz/application/ports/` no contiene `Session`, tablas ni expresiones SQL (`grep` sin resultados para `sqlalchemy`/`Session` en `src/voz/application`). | No |
| Routers solo traducen transporte | Cada router es una función `create_*_router(...)` que recibe casos de uso o repositories ya construidos y traduce errores tipados a `{"detail": {"code", "message"}}`. Cubierto por `tests/integration/test_*_api.py`. | Sí, comportamiento; no la ausencia de lógica. |
| Los adapters se instancian en el composition root | `Sqlite*Repository`, `FileSystemMediaStorage`, `FfprobeMediaProbe`, `FfmpegMediaNormalizer`, `FasterWhisperProvider` y `FileSystemModelStore` se construyen en `create_app()` y `create_local_asr_runtime()` (`src/voz/bootstrap.py`). Excepción: `interfaces/cli/doctor.py` construye sondas de solo lectura. `tests/unit/test_asr_bootstrap.py` cubre la composición ASR sin descargas. | Parcial |
| Sin rutas del host hacia la UI | El esquema no tiene columnas de ruta (`src/voz/infrastructure/persistence/schema.py`; `test_schema_and_adapters_never_persist_host_paths` en `tests/unit/infrastructure/persistence/test_repositories.py`). Destinos de disco derivados de UUID. Tests: `test_health_api.py` (sin rutas sensibles), `test_media_upload_api.py`, `test_media_stream_api.py::test_deleted_original_file_is_reported_missing_without_path`. | Sí |
| Jobs largos con estado, progreso, cancelación y recuperación | `TranscriptionJobState` con 12 estados y transiciones validadas (`src/voz/domain/entities/transcription_job.py`); `JobRunner` con hilo, cancelación cooperativa y `recover()` (`src/voz/application/job_runner.py`); `tests/integration/application/test_job_runner.py`. | Sí |
| Los providers pasan contract tests comunes | `tests/contract/test_transcription_provider.py` parametriza un provider estructural y `FasterWhisperProvider` con un engine falso. Detalle en [ADR-0005](0005-transcription-providers.md). | Sí |
| Funciona offline con modelos instalados | Ver [ADR-0006](0006-local-first-privacy.md). | Parcial |

### Implementación real frente a lo escrito arriba

Puntos donde el código difiere de la redacción inicial de esta ADR, sin cambiar
la decisión:

- **Pipeline «asíncrono»**: los jobs corren en un único hilo daemon
  (`JobRunner`, cola `queue.Queue` en memoria), no en corrutinas ni procesos.
  El trabajo pesado no corre en el event loop: las rutas con SQLite o disco son
  funciones síncronas (`def`, que FastAPI ejecuta en su threadpool) o usan
  `run_in_threadpool`/`anyio.to_thread` (`media.py`, `media_stream.py`,
  `job_events.py`).
  Escalar a varios workers o procesos queda **planificado** (`ponytail:` en
  `job_runner.py`).
- **SSE**: el endpoint `GET /api/jobs/{id}/events` sondea el repositorio cada
  ~500 ms; no hay bus de eventos interno (`src/voz/interfaces/api/job_events.py`).
  Un pub/sub en proceso queda **planificado** si el sondeo deja de bastar.
- **Contratos `DiarizationProvider` y `AlignmentProvider`**: no existen todavía.
  Solo `TranscriptionProvider` está implementado. Ver ADR-0005.
- **Web UI**: el bundle compilado se sirve como estático desde `src/voz/static`
  con `StaticFiles`; no hay proceso separado.

### Deuda de frontera conocida

- `interfaces/api/media_stream.py` recibe el adapter concreto
  `FileSystemMediaStorage` para resolver la ruta que sirve `FileResponse`. La
  ruta nunca llega al navegador, pero un port de lectura de originales sería
  más simétrico.
- No hay una guarda automática que recorra todo `src/voz/application` y
  `src/voz/domain` con una lista completa de imports prohibidos (frameworks,
  `voz.infrastructure`, `voz.interfaces`, SDKs de proveedores). **Planificado**:
  un test de AST al estilo del test de dominio existente, sin añadir
  dependencias.

## Reglas de cumplimiento

Esta decisión se considera respetada cuando:

- `domain` no importa paquetes de frameworks o proveedores;
- casos de uso dependen de ports y no de SQL/FFmpeg/SDKs concretos;
- routers no contienen reglas de negocio;
- la UI no recibe rutas absolutas del host;
- los proveedores pasan contract tests comunes;
- el proceso funciona offline con modelos ya instalados;
- los jobs largos persisten progreso recuperable.

Cambiar estas reglas requiere una nueva ADR que sustituya explícitamente esta
decisión.
