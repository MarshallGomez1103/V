# VOZ

VOZ es un proyecto local-first para transcribir, revisar y exportar grabaciones
largas de clases, entrevistas y reuniones. La meta es ofrecer un workspace web
local con waveform, timeline, segmentos editables y hablantes, sin convertir un
proveedor cloud en requisito.

> **Estado actual: ingestión backend verificable.** La CLI, la API health y la
> Home local funcionan como una sola aplicación instalable. El backend ya puede
> inspeccionar, conservar y normalizar medios localmente, aunque la selección de
> archivos todavía no está conectada a la UI y aún no existe un motor ASR
> integrado. Este repositorio todavía no transcribe audio con Faster Whisper,
> whisper.cpp, OpenAI o ElevenLabs. Consulta el [roadmap](ROADMAP.md) para ver
> qué fue realmente verificado.

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
[ADR-0003](docs/adr/0003-ffmpeg-ingestion.md).

## Desarrollo local

No hay release pública todavía. Para instalar el checkout y ejecutar la Home
local integrada:

```bash
uv sync --all-groups
uv run voz --no-browser
```

La aplicación queda disponible en `http://127.0.0.1:8765` y expone
`GET /api/health`. Para modificar y reconstruir el frontend:

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
- [Setup de desarrollo en Bazzite](docs/development/setup-bazzite.md)
