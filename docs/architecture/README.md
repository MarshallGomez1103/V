# Arquitectura de VOZ

Esta carpeta documenta la arquitectura **tal como existe hoy en el código**,
con el modelo C4 (Simon Brown) en tres niveles. Lo que solo está en el plan
maestro se marca como **planificado** y se dibuja con línea punteada. Las
decisiones duraderas viven en los [ADR](../adr/README.md); estos diagramas las
ilustran y no las sustituyen.

| Nivel | Documento | Pregunta que responde |
| --- | --- | --- |
| C4-1 Contexto | [01-contexto.md](01-contexto.md) | ¿Quién usa VOZ y con qué sistemas externos habla? |
| C4-2 Contenedores | [02-contenedores.md](02-contenedores.md) | ¿Qué procesos, almacenes y binarios componen una instalación? |
| C4-3 Componentes | [03-componentes.md](03-componentes.md) | ¿Cómo se reparte el código en capas y qué depende de qué? |

## Convenciones

- Los diagramas son `flowchart`/`sequenceDiagram` de Mermaid porque GitHub los
  renderiza de forma fiable; no se usa la sintaxis experimental `C4Context`.
- Línea continua: existe y está cableado en `src/voz/bootstrap.py`.
- Línea punteada y etiqueta «planificado»: aparece en
  [VOZ_PLAN_MAESTRO.md](../../VOZ_PLAN_MAESTRO.md) o en el
  [ROADMAP](../../ROADMAP.md), pero no en el código.
- Las rutas de archivo son relativas a la raíz del repositorio. Las rutas de
  runtime (`~/.local/share/voz/...`) son las de un usuario Linux sin variables
  `XDG_*` personalizadas; ver [ADR-0002](../adr/0002-sqlite-persistence.md).

## ADR relacionados

| ADR | Tema |
| --- | --- |
| [0001](../adr/0001-modular-monolith.md) | Monolito modular y límites hexagonales |
| [0002](../adr/0002-sqlite-persistence.md) | SQLite, Alembic y layout de filesystem XDG |
| [0003](../adr/0003-ffmpeg-ingestion.md) | Ingestión FFmpeg sobre originales inmutables |
| [0004](../adr/0004-local-asr-and-recoverable-chunks.md) | Faster Whisper local y chunks recuperables |
| [0005](../adr/0005-transcription-providers.md) | Port de providers, registry y regla de no plugins |
| [0006](../adr/0006-local-first-privacy.md) | Local-first, loopback y sin cloud implícito |

## Mantenimiento

Un cambio que añada un contenedor, un adapter, un provider o una dependencia de
capa debe actualizar el diagrama afectado en el mismo cambio (regla de
[AGENTS.md](../../AGENTS.md): «Durable changes to architecture require a new or
updated ADR»).
