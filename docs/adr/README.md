# Registro de decisiones de arquitectura (ADR)

Cada ADR registra una decisión duradera, su contexto, consecuencias, alternativas
descartadas y evidencia verificable en el código. Un cambio de arquitectura debe
crear o actualizar un ADR (regla de [AGENTS.md](../../AGENTS.md)). Los diagramas
que las ilustran están en [docs/architecture](../architecture/README.md).

| ADR | Título | Estado | Roadmap |
| --- | --- | --- | --- |
| [0001](0001-modular-monolith.md) | Monolito modular local con arquitectura hexagonal | Aceptada | S16.12 |
| [0002](0002-sqlite-persistence.md) | SQLite, migraciones Alembic y layout de filesystem XDG | Aceptada | S16.13 |
| [0003](0003-ffmpeg-ingestion.md) | Ingestión FFmpeg sobre originales inmutables | Aceptada | S16.14 |
| [0004](0004-local-asr-and-recoverable-chunks.md) | ASR local con modelos explícitos y chunks recuperables | Aceptada | S4 |
| [0005](0005-transcription-providers.md) | Port de providers de transcripción sin framework de plugins | Aceptada | S16.15 |
| [0006](0006-local-first-privacy.md) | Local-first, loopback por defecto y sin cloud implícito | Aceptada | S16.16 |

## Formato

Encabezado con estado, fecha, responsables, alcance y (si aplica) última
revisión; luego Contexto, Decisión, Consecuencias positivas, Costes y límites,
Alternativas consideradas, Evidencia actual (rutas de archivos y tests reales) y
Verificación. Lo que aún no existe en el código se marca como **planificado**.
