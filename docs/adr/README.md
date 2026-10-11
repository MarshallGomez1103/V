# Architecture Decision Records (ADR)

Each ADR records a durable decision, its context, consequences, rejected
alternatives and verifiable evidence in the code. An architecture change must
create or update an ADR (rule in [AGENTS.md](../../AGENTS.md)). The diagrams
that illustrate them are in [docs/architecture](../architecture/README.md).

ADRs 0001 to 0008 were written in Spanish and translated to English on
2026-10-11 (V1-08b); number, date, status and decision are unchanged. They use
the former product name VOZ where they describe that moment (see
[ADR-0009](0009-rename-to-v.md)).

| ADR | Title | Status | Roadmap |
| --- | --- | --- | --- |
| [0001](0001-modular-monolith.md) | Local modular monolith with hexagonal architecture | Accepted | S16.12 |
| [0002](0002-sqlite-persistence.md) | SQLite, Alembic migrations and the XDG filesystem layout | Accepted | S16.13 |
| [0003](0003-ffmpeg-ingestion.md) | FFmpeg ingestion over immutable originals | Accepted | S16.14 |
| [0004](0004-local-asr-and-recoverable-chunks.md) | Local ASR with explicit models and recoverable chunks | Accepted | S4 |
| [0005](0005-transcription-providers.md) | Transcription provider port without a plugin framework | Accepted | S16.15 |
| [0006](0006-local-first-privacy.md) | Local-first, loopback by default and no implicit cloud | Accepted | S16.16 |
| [0007](0007-local-diarization-sherpa-onnx.md) | Local diarization with sherpa-onnx (no torch, no token) | Accepted | S6.04, S6.16 |
| [0008](0008-word-timestamps.md) | Native word timestamps from Faster Whisper, without WhisperX | Accepted | S7.01, S7.03, S7.04, S7.08 |
| [0009](0009-rename-to-v.md) | Rename the product to V with compatibility (`v` + `voz` alias, internals unchanged) | Accepted | V1-01 |

## Format

A header with status, date, owners, scope and (if applicable) last review; then
Context, Decision, Positive consequences, Costs and limits, Alternatives
considered, Current evidence (paths of real files and tests) and Verification.
Anything that does not yet exist in the code is marked **planned**.
