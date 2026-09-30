# ADR-0002: SQLite con mapeo explícito y migraciones Alembic

- Estado: Aceptada
- Fecha: 2026-09-02
- Responsables: mantenedores de VOZ
- Alcance: persistencia local inicial: SQLite, migraciones y layout de filesystem XDG
- Última revisión: 2026-09-30 (S16.13; corrige el nombre del archivo y añade el
  layout de filesystem)
- Diagramas: [contenedores](../architecture/02-contenedores.md)

## Contexto

VOZ necesita que proyectos, medios, transcripciones, hablantes y jobs sobrevivan
al cierre de la aplicación. El producto se ejecuta para una persona en una sola
máquina y no necesita un servidor de base de datos. Al mismo tiempo, el dominio
no debe depender de SQLAlchemy ni adoptar detalles de tablas como reglas de
negocio.

Los jobs largos también requieren escrituras incrementales y lecturas
concurrentes desde la UI. La evolución del esquema debe ser reproducible y no
puede depender de crear tablas implícitamente en cada arranque.

## Decisión

La primera implementación persistente utilizará SQLite mediante SQLAlchemy 2,
con migraciones versionadas en Alembic y `journal_mode=WAL` activado por cada
conexión del adapter.

- El archivo predeterminado es `~/.local/share/voz/voz.sqlite3`
  (`DATABASE_FILENAME` en `src/voz/bootstrap.py`), resuelto por el módulo XDG
  existente. La redacción original de esta ADR decía `voz.db`; el código nunca
  usó ese nombre.
- Los contratos de repositories vivirán en `application/ports` y trabajarán con
  entidades del dominio.
- Tablas, metadata y conversión fila-entidad vivirán exclusivamente en
  `infrastructure/persistence`.
- Las entidades del dominio no serán modelos ORM y no importarán SQLAlchemy.
- La migración inicial será la fuente autoritativa del esquema distribuido.
- Las pruebas podrán crear un engine SQLite temporal sin escribir datos en el
  checkout ni en los directorios XDG reales.
- Cada operación de repository tiene un límite transaccional explícito (cada
  método abre `engine.begin()` o `engine.connect()`). Una futura unidad de
  trabajo podrá coordinar varias operaciones si aparece un caso de uso que lo
  necesite. Hoy la única escritura multi-tabla atómica es el commit de chunk
  (segmentos, checkpoint y job) en `SqliteTranscriptionCheckpointStore`
  ([ADR-0004](0004-local-asr-and-recoverable-chunks.md)).
- Cada conexión activa `foreign_keys=ON`, `journal_mode=WAL` y
  `busy_timeout` (por defecto 5 000 ms); `create_sqlite_engine` exige una ruta
  absoluta y no tiene valor por defecto ligado al checkout o al directorio de
  trabajo.
- La migración se aplica en el lifespan de la aplicación con
  `upgrade_to_head` (`src/voz/infrastructure/persistence/migrate.py`), nunca al
  importar el módulo, y es idempotente. Los scripts viven en
  `migrations/versions/` (checkout) o dentro del wheel
  (`pyproject.toml`, `force-include`).

## Filesystem y XDG

La base de datos no contiene los medios: guarda identidad, hash, tamaño,
duración, tipo y nombre visible. Los bytes viven en el filesystem bajo
directorios XDG resueltos por `resolve_voz_paths` (`src/voz/infrastructure/paths.py`),
que ignora variables `XDG_*` vacías o relativas.

| Ubicación (sin variables `XDG_*`) | Contenido | Quién lo escribe |
| --- | --- | --- |
| `~/.local/share/voz/voz.sqlite3` (+ `-wal`, `-shm`) | Base de datos | `create_sqlite_engine` |
| `~/.local/share/voz/projects/<project_uuid>/originals/<media_uuid>.original` | Original inmutable, permisos de solo lectura | `FileSystemMediaStorage` |
| `~/.local/share/voz/projects/<project_uuid>/derivatives/<media_uuid>.inference.wav` | Derivado PCM mono 16 kHz | `FfmpegMediaNormalizer` |
| `~/.local/share/voz/models/` | Modelos instalados con manifest | `FileSystemModelStore` |
| `~/.cache/voz/uploads/` | Staging de subidas HTTP, borrado en todos los caminos | `interfaces/api/media.py` |
| `~/.cache/voz/downloads/` | Metadatos de descarga de modelos | `FileSystemModelStore` |
| `~/.config/voz/`, `~/.local/state/voz/` | Resueltos y comprobados por `voz doctor`; el código no escribe en ellos todavía | Nadie |

Reglas:

- Nada de runtime se escribe dentro del checkout; las pruebas usan `tmp_path`.
- Ninguna ruta de disco se guarda en SQLite ni se envía al navegador: los
  destinos se derivan de UUID (`original_path_for`, `FfmpegMediaNormalizer`).
  `test_schema_and_adapters_never_persist_host_paths` lo comprueba.
- No existe una transacción que abarque SQLite y filesystem. La consistencia se
  logra ordenando las operaciones y compensando: `ImportMedia` publica el
  original, persiste la fila y, si la fila falla, descarta el original; si el
  resultado es ambiguo, reconcilia antes de borrar
  ([ADR-0003](0003-ffmpeg-ingestion.md)).
- Los originales son inmutables; todo derivado se escribe en otro directorio.

**Planificado, no implementado:** `projects/<id>/chunks|exports|artifacts`,
`~/.cache/voz/waveforms|temp`, `~/.config/voz/config.toml`, respaldo o
exportación de la base de datos y política de retención/borrado de proyectos.

## Consecuencias positivas

- No hay servicio externo que instalar o administrar.
- WAL permite que las lecturas locales continúen mientras se confirman
  escrituras cortas.
- El dominio puede probarse sin base de datos.
- Los adapters pueden sustituirse sin cambiar los casos de uso.
- Alembic deja una ruta auditable para evolucionar el esquema.

## Costes y límites

- SQLite sigue siendo almacenamiento de un solo equipo, no multiusuario remoto.
- Hay conversión explícita entre filas y entidades.
- Las operaciones síncronas no deben ejecutarse en el event loop durante jobs
  pesados; la capa de aplicación deberá enviarlas a un worker cuando aplique.
- WAL crea archivos auxiliares `-wal` y `-shm`, que son datos de ejecución y no
  pertenecen a Git.

## Alternativas consideradas

### Postgres

Rechazado para la primera versión. Añade instalación, credenciales y un proceso
externo sin aportar valor al caso local de un usuario.

### ORM dentro del dominio

Rechazado. Acoplaría invariantes y tests centrales al ciclo de vida de
SQLAlchemy y dificultaría sustituir la persistencia.

### Guardar los medios como BLOB dentro de SQLite

Rechazada. Las grabaciones pesan gigabytes; el archivo de base de datos y su
WAL crecerían sin control, y FFmpeg y el reproductor necesitan descriptors de
archivo. Se guarda el hash SHA-256 como identidad del contenido.

### Guardar rutas absolutas en la base de datos

Rechazada. Vincula la base al layout del host, facilita fugas hacia la API y
rompe al mover el directorio de datos. Los destinos se derivan de UUID.

### Ubicar la base de datos en el checkout o en el directorio de trabajo

Rechazada. Mezclaría datos privados con código y con Git; contradice la regla
XDG de [AGENTS.md](../../AGENTS.md).

### Crear tablas automáticamente sin migraciones

Rechazado como mecanismo de distribución. Puede ser útil en fixtures de tests,
pero no registra cómo evoluciona una base existente.

## Evidencia actual (2026-09-30)

| Requisito | Prueba o código |
| --- | --- |
| Pragmas por conexión y reapertura WAL | `tests/integration/persistence/test_database.py` |
| Migraciones equivalentes a la metadata y downgrade seguro | `tests/integration/persistence/test_migrations.py` |
| Migración idempotente al arrancar | `tests/integration/persistence/test_runtime_migrate.py` |
| Repositories reconstruyen entidades y sobreviven a la reapertura del engine | `tests/integration/persistence/test_sqlite_repositories.py`, `tests/unit/infrastructure/persistence/test_repositories.py` |
| Selección de job reproducible en SQLite | `tests/integration/persistence/test_sqlite_job_selections.py` |
| Sin rutas del host en el esquema | `test_schema_and_adapters_never_persist_host_paths` |
| Resolución XDG con overrides absolutos y fallback | `tests/unit/test_xdg_paths.py` |
| Importación con compensación filesystem/SQLite | `tests/integration/application/test_import_media_sqlite.py`, `tests/unit/application/test_import_media.py` |
| Dominio sin SQLAlchemy | `tests/unit/domain/test_entity_invariants.py` |

Esquema actual (`schema.py`): `projects`, `media_assets`, `transcripts`,
`segments`, `words`, `speakers`, `speaker_turns`, `transcription_jobs`,
`transcription_checkpoints`, `transcription_job_selections`.

## Verificación

La decisión se considera implementada cuando:

- ningún módulo bajo `domain` importa SQLAlchemy;
- los ports no exponen `Session`, tablas ni expresiones SQL;
- la migración inicial crea todas las tablas de la Sección 2;
- una conexión nueva reporta `journal_mode=wal` cuando el archivo lo permite;
- repositories reconstruyen entidades equivalentes después de cerrar y abrir
  otro engine sobre el mismo archivo;
- las pruebas usan rutas temporales y no crean `voz.sqlite3` en el repositorio;
- ninguna ruta del host se persiste ni se devuelve por HTTP;
- los datos de runtime solo se escriben bajo los directorios XDG resueltos.
