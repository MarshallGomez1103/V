# VOZ

VOZ es un proyecto local-first para transcribir, revisar y exportar grabaciones
largas de clases, entrevistas y reuniones. La meta es ofrecer un workspace web
local con waveform, timeline, segmentos editables y hablantes, sin convertir un
proveedor cloud en requisito.

> **Estado actual: importación desde la UI y selector de motor.** La CLI, la
> API y la Home local funcionan como una sola aplicación instalable. Desde el
> navegador ya se crea un proyecto, se sube un archivo (copia inmutable con
> SHA-256 y ffprobe) y se elige el motor entre las opciones que expone el
> backend, y se crea un job que un ejecutor en segundo plano normaliza,
> transcribe por chunks con checkpoints SQLite y publica por SSE hasta la lista
> de segmentos. Los jobs interrumpidos se reanudan al arrancar. Existen
> exportadores TXT, Markdown, SRT, VTT y JSON canónico (sin endpoint HTTP
> todavía) y `voz doctor` diagnostica FFmpeg, puerto, rutas, runtime y GPU.
> El flujo completo solo se ha ejercitado con un motor determinista de
> pruebas: con Faster Whisper real sigue siendo experimental. No se incluye
> ni descarga ningún
> modelo: el runtime real permanece experimental hasta instalar un modelo
> elegido explícitamente y ejecutar el smoke opt-in. Consulta el
> [roadmap](ROADMAP.md) para ver qué fue verificado.

## Visión

La experiencia objetivo es:

```text
$ voz

VOZ 0.x
Servidor: http://127.0.0.1:8765
Abriendo navegador...
```

Desde la interfaz, el usuario podrá importar un archivo que FFmpeg pueda
decodificar, elegir un perfil de procesamiento, seguir el progreso, corregir el
transcript y exportarlo. Los originales serán inmutables y los resultados de
trabajos largos se guardarán incrementalmente.

## Principios

- local y privado por defecto;
- funcionamiento offline con modelos ya descargados;
- motores intercambiables detrás de contratos comunes;
- UI siempre responsiva mediante jobs asíncronos;
- originales inmutables y procesamiento reproducible;
- recuperación mediante checkpoints para grabaciones largas;
- arquitectura extensible sin microservicios prematuros.

## Alcance planificado

El MVP comprende:

- CLI `voz` y servidor web local;
- importación y normalización con FFmpeg;
- transcripción local con Faster Whisper;
- progreso y reanudación de trabajos largos;
- edición sincronizada con waveform;
- diarización editable de hablantes;
- exportación TXT, Markdown, SRT, VTT y JSON.

Después del MVP se evaluarán word alignment, whisper.cpp, administración avanzada
de modelos y proveedores cloud opcionales. La lista autoritativa, con IDs
estables y estado verificable, está en [ROADMAP.md](ROADMAP.md).

## Privacidad

VOZ está diseñado para enlazarse únicamente a `127.0.0.1` por defecto. Un
proveedor cloud nunca debe activarse implícitamente: el usuario tendrá que
configurarlo y seleccionarlo de forma explícita.

No deben entrar en Git:

- grabaciones o transcripts privados;
- modelos y archivos multimedia generados;
- bases de datos, caches o datos XDG de ejecución;
- claves API, `.env` o secretos;
- contexto local de agentes en `.ai/`.

No uses grabaciones privadas como fixtures de pruebas.

## Arquitectura

VOZ adopta un monolito modular local con límites Clean/Hexagonal:

```text
React UI
   |
FastAPI / Typer interfaces
   |
Application use cases and ports
   |
Domain
   ^
Infrastructure adapters: SQLite, FFmpeg, ASR, diarization, cloud
```

El dominio no depende de FastAPI, SQLAlchemy, FFmpeg, torch ni SDKs externos.
Los detalles y consecuencias están documentados en
[ADR-0001](docs/adr/0001-modular-monolith.md). La frontera multimedia y sus
garantías de integridad están en
[ADR-0003](docs/adr/0003-ffmpeg-ingestion.md). La instalación local explícita,
selección de hardware y recuperación ASR están en
[ADR-0004](docs/adr/0004-local-asr-and-recoverable-chunks.md).

## Desarrollo local

La consulta `GET /api/transcription-options` expone opciones conocidas,
registro local, disponibilidad del runtime, ejecución y bloqueos sin cargar
modelos. Su [contrato y límites](docs/api/transcription-options.md) distinguen
registro de integridad y recomendación de benchmark. Los endpoints de
proyectos, subida, jobs y eventos SSE están descritos en
[docs/api/jobs.md](docs/api/jobs.md). Los datos viven bajo XDG
(`$XDG_DATA_HOME/voz/voz.sqlite3`, originales y derivados por proyecto) y el
esquema se migra automáticamente al arrancar.

Para retomar el desarrollo en otra sesión, lee `AGENTS.md`, el apartado
“Retomar en una sesión nueva” de [ROADMAP.md](ROADMAP.md) y `.ai/HANDOFF.md`
cuando exista. Los próximos cortes propuestos están al final del tablero de
Sección 5 en el roadmap.

No hay release pública todavía. Para instalar el checkout y ejecutar la Home
local integrada:

```bash
uv sync --all-groups
uv run voz --no-browser
```

El runtime Faster Whisper es opcional y no altera el bootstrap ordinario:

```bash
uv sync --all-groups --extra asr-local
```

Ese comando instala la dependencia, no los pesos. La instalación de un modelo
requiere un descriptor con repositorio y SHA de commit de 40 caracteres, además
de confirmación explícita. Para probar un directorio de modelo ya instalado sin
red, se ofrece un smoke CPU opt-in:

```bash
VOZ_FASTER_WHISPER_MODEL_DIR=/ruta/al/model \
VOZ_FASTER_WHISPER_MODEL_SOURCE=organizacion/repositorio \
VOZ_FASTER_WHISPER_MODEL_REVISION=sha_git_de_40_caracteres \
  uv run pytest tests/integration/application/test_faster_whisper_real_opt_in.py
```

CUDA continúa rotulado como experimental hasta ejercitarlo en hardware real.

La aplicación queda disponible en `http://127.0.0.1:8765` y expone
`GET /api/health`. Para revisar prerrequisitos sin arrancar el servidor:

```bash
uv run voz doctor          # añade --json o --redact si lo necesitas
``` Para modificar y reconstruir el frontend:

```bash
cd apps/web
npm ci
npm run build
```

Para Bazzite/Fedora Atomic consulta la
[guía de setup](docs/development/setup-bazzite.md). No se recomienda modificar la
imagen base con `rpm-ostree` para el bootstrap ordinario.

## Comprobaciones previstas

Backend:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

Frontend:

```bash
cd apps/web
npm run lint
npm run typecheck
npm run test
npm run build
```

Un item del roadmap solo se marca como terminado después de ejecutar y registrar
las comprobaciones aplicables.

## Colaboración

Antes de trabajar lee [AGENTS.md](AGENTS.md), selecciona entre uno y tres items
estrechamente relacionados del roadmap y registra la asignación. Las decisiones
arquitectónicas durables se documentan como ADR; las notas privadas y transitorias
de sesión permanecen en `.ai/` y no se versionan.

La contribución externa todavía no está abierta formalmente: faltan la guía de
contribución, políticas comunitarias, plantillas y una versión publicable. Esos
trabajos están registrados en la Sección 16.

## Licencia

VOZ se distribuye bajo la [licencia MIT](LICENSE). Cualquier código de terceros
incorporado deberá conservar sus avisos y quedar registrado en `NOTICE` cuando
corresponda.

## Documentación de planificación

- [Plan maestro](VOZ_PLAN_MAESTRO.md)
- [Roadmap ejecutable](ROADMAP.md)
- [Reglas de ingeniería](AGENTS.md)
- [ADR-0001: monolito modular](docs/adr/0001-modular-monolith.md)
- [ADR-0002: persistencia SQLite](docs/adr/0002-sqlite-persistence.md)
- [ADR-0003: ingestión FFmpeg](docs/adr/0003-ffmpeg-ingestion.md)
- [ADR-0004: ASR local recuperable](docs/adr/0004-local-asr-and-recoverable-chunks.md)
- [Setup de desarrollo en Bazzite](docs/development/setup-bazzite.md)
