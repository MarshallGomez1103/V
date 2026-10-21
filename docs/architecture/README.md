# V architecture

V is a local-first voice workspace. This folder documents its
architecture **as it exists in the code today**, using the C4 model (Simon
Brown) at three levels. Anything that only exists in the master plan is marked
**planned** and drawn with a dashed line. Durable decisions live in the
[ADRs](../adr/README.md); these diagrams illustrate them and do not replace
them.

| Level | Document | Question it answers |
| --- | --- | --- |
| C4-1 Context | [01-contexto.md](01-contexto.md) | Who uses V, and which external systems does it talk to? |
| C4-2 Containers | [02-contenedores.md](02-contenedores.md) | Which processes, data stores and binaries make up an installation? |
| C4-3 Components | [03-componentes.md](03-componentes.md) | How is the code split into layers, and what depends on what? |

The file names keep their original Spanish form (`contexto`, `contenedores`,
`componentes`) so that existing links keep working.

## Conventions

- Diagrams are Mermaid `flowchart`/`sequenceDiagram` because GitHub renders
  them reliably; the experimental `C4Context` syntax is not used.
- Solid line: it exists and is wired in `src/voz/bootstrap.py`.
- Dashed line and the label "planned": it appears in
  [VOZ_PLAN_MAESTRO.md](../../VOZ_PLAN_MAESTRO.md) (the master plan, in
  Spanish) or in the [ROADMAP](../../ROADMAP.md), but not in the code.
- File paths are relative to the repository root. Runtime paths
  (`~/.local/share/voz/...`) are those of a Linux user without custom `XDG_*`
  variables; see [ADR-0002](../adr/0002-sqlite-persistence.md).
- Internal identifiers keep the old name on purpose (Python package `voz`,
  directories `voz`, `VOZ_*` variables); see
  [ADR-0009](../adr/0009-rename-to-v.md).

## Related ADRs

| ADR | Topic |
| --- | --- |
| [0001](../adr/0001-modular-monolith.md) | Modular monolith and hexagonal boundaries |
| [0002](../adr/0002-sqlite-persistence.md) | SQLite, Alembic and the XDG filesystem layout |
| [0003](../adr/0003-ffmpeg-ingestion.md) | FFmpeg ingestion over immutable originals |
| [0004](../adr/0004-local-asr-and-recoverable-chunks.md) | Local Faster Whisper and recoverable chunks |
| [0005](../adr/0005-transcription-providers.md) | Provider port, registry and the no-plugins rule |
| [0006](../adr/0006-local-first-privacy.md) | Local-first, loopback and no implicit cloud |
| [0007](../adr/0007-local-diarization-sherpa-onnx.md) | Local diarization with sherpa-onnx |
| [0008](../adr/0008-word-timestamps.md) | Native word timestamps from Faster Whisper |
| [0009](../adr/0009-rename-to-v.md) | Rename to V with backward compatibility |

## Maintenance

A change that adds a container, an adapter, a provider or a layer dependency
must update the affected diagram in the same change (rule from
[AGENTS.md](../../AGENTS.md): "Durable changes to architecture require a new or
updated ADR").
