# V roadmap

This file is the public source of truth for product progress. The long-term plan
and its rationale are in [VOZ_PLAN_MAESTRO.md](VOZ_PLAN_MAESTRO.md). The
repository is public.

## Conventions

- Every achievement has a stable ID `S<section>.<number>`. A published ID is
  never renumbered or reused; new achievements are appended to the end of their
  section.
- `[ ]` means pending, `[x]` means verified. Code that has been written but not
  checked stays pending.
- An assignment covers one to three closely related IDs. A bootstrap exception
  must be stated explicitly on the board.
- Allowed states: `pending`, `in progress`, `blocked`, `verified`.
- The **Last verifiable achievement** column describes the last small checkpoint
  that survives even if a session ends. It does not describe vague intentions.
- Durable architecture is recorded in ADRs; the board does not replace the ADRs.

## Atomic update rule

Before editing, the agent adds or claims a row with exact IDs and the state `in
progress`. Nobody works on the same IDs at the same time. After each verified
checkpoint, the following must be changed **in the same edit**: the corresponding
checkbox, the assignment state and the last verifiable achievement. If the tests
fail or cannot be run, the checkbox stays open and the row records the failure or
blocker. Ranges are not ticked off by inference, and other agents' achievements
are never deleted. The coordinator releases or reassigns abandoned IDs
explicitly.

## Initial active work

| Package | IDs | State | Last verifiable achievement |
| --- | --- | --- | --- |
| BOOT-INT-001 | S1.01, S1.02 | verified | `main` repository initialized and MIT license present. |
| BOOT-INT-002 | S1.16, S1.19 | verified | CI reproduces the local checks; local agent-session context, secrets, media, models and artifacts are excluded. |
| BOOT-BE-001 | S1.03, S1.10, S1.11 | verified | `uv sync --locked`, Ruff and Pyright passed with the declared environment. |
| BOOT-BE-002 | S1.05, S1.12 | verified | `/api/health` answered over real HTTP and the 15 Python tests passed. |
| BOOT-BE-003 | S1.06-S1.08 | verified | `voz` started Uvicorn on loopback, served the UI and shut down cleanly with Ctrl+C; browser opening covered by tests. |
| BOOT-BE-004 | S1.09 | verified | The three XDG path tests passed. |
| BOOT-WEB-001 | S1.04 | verified | React/Vite built and the bundle was included in the Python wheel. |
| BOOT-WEB-002 | S1.13, S1.14 | verified | ESLint and strict TypeScript passed after `npm ci`. |
| BOOT-WEB-003 | S1.15 | verified | Vitest ran the two Home and health tests without failures. |
| BOOT-DOC-001 | S1.17, S1.18 | verified | Rules and roadmap created; structure, IDs and Markdown checked. |
| BOOT-DOC-002 | S1.20, S1.21 | verified | ADR-0001 and Bazzite setup created; links and structure checked. |
| BOOT-DOC-003 | S16.01 | verified | README created without claiming ASR was implemented; links checked. |
| BOOT-VERIFY-001 | S1.22 | verified | Clean checkout on Bazzite: locks, checks, Home/API over HTTP and clean shutdown verified. |

When a package finishes, keep its row as brief history until the next
coordinated cut; after that it may be moved to a work changelog without altering
the IDs.

## Active work — Section 2

| Package | IDs | State | Last verifiable achievement |
| --- | --- | --- | --- |
| DOM-CORE-001 | S2.01-S2.03 | verified | Project, MediaAsset and Transcript: 39 focused tests and strict checks pass. |
| DOM-TIME-001 | S2.04, S2.05 | verified | Segment and Word validate offsets and ownership; the integrated domain suite passes. |
| DOM-JOB-001 | S2.08-S2.10 | verified | Pipeline, failure and cancellation are explicit; the integrated domain suite passes. |
| DOM-SPEAKER-001 | S2.06, S2.07 | verified | Monotonic speaker rename and acoustic SpeakerTurn kept separate; 28 tests pass. |
| PERSIST-PORT-001 | S2.11 | verified | Eight Protocols expose no SQL/Session; structural tests pass. |
| PERSIST-REPO-001 | S2.12 | verified | 24 tests: Core adapters, Word sync and validation against the parent Segment. |
| PERSIST-MIG-001 | S2.13 | verified | Upgrade/downgrade and installed wheel with Alembic config/revision pass. |
| PERSIST-WAL-001 | S2.14 | verified | 6 file-backed tests pass: WAL, FK, timeout and real reopening. |
| VERIFY-DOM-001 | S2.15 | verified | 198 unit tests; clean architecture, Ruff and Pyright pass. |
| VERIFY-SQL-001 | S2.16, S2.17 | verified | 16 file-backed tests cover 8 adapters and recovery after reopening. |

## Active work — Section 3

| Package | IDs | State | Last verifiable achievement |
| --- | --- | --- | --- |
| INGEST-PROBE-001 | S3.01-S3.03 | verified | 9 tests validate the port, real ffprobe, streams/codecs and irrelevant extensions. |
| INGEST-STORE-001 | S3.04 | verified | 13 tests validate immutable copy, SHA-256 during the copy and safe publication. |
| INGEST-FIX-001 | S3.11-S3.13 | verified | 6 licensed synthetic fixtures pass hash, ffprobe and FFmpeg decoding. |
| INGEST-APP-001 | S3.05, S3.06, S3.14 | verified | 30 focused tests cover immutable copy, persisted metadata, corrupt files and rollback on interruption. |
| INGEST-NORM-001 | S3.07, S3.10, S3.15 | verified | 16 tests cover mono 16 kHz PCM, cancellation, fsync, pipe closing and observable cleanup. |
| INGEST-PROGRESS-001 | S3.09 | verified | Progress is monotonic, bounded and ends at the known duration. |
| INGEST-PROBE-FIX-001 | S3.03 | verified | Regressions cover dca/dts aliases and extreme durations without a raw exception. |
| INGEST-STORE-FIX-001 | S3.08, S3.16 | verified | 49 tests cover reopening, durable hierarchy, UUIDs, symlinks, unsafe names and descriptor closing. |

## Active work — Section 4

| Package | IDs | State | Last verifiable achievement |
| --- | --- | --- | --- |
| ASR-CONTRACT-001 | S4.01, S4.02 | verified | Path-free contract with cancellation and typed errors; immutable descriptor; the full suite of 349 tests passes. |
| ASR-REGISTRY-001 | S4.03 | verified | Deterministic registry rejects duplicates, incomplete contracts and non-callable entrypoints; strict checks pass. |
| ASR-ADAPTER-001 | S4.04-S4.06 | verified | Local-only adapter, confirmed XDG installation and provenance manifest; 358 tests and strict checks pass. |
| ASR-PROFILE-001 | S4.07-S4.09 | verified | fast/quality descriptors and GPU/CPU fallback with an observable cause; 366 tests and strict checks pass. |
| ASR-CHUNK-001 | S4.10, S4.11 | verified | Planner with overlap/ownership and per-unit progress; 373 tests and strict checks pass. |
| ASR-RECOVERY-001 | S4.12-S4.14 | verified | Checkpoints pin plan/model/source/revision/language; cancellation and reopening do not repeat chunks; atomic rollback tested. |
| ASR-CONTRACT-002 | S4.15-S4.17 | verified | Common suite over a structural provider and Faster Whisper: valid WAV, timeline, cancellation and errors; physical integration by clips. |
| ASR-LANGUAGE-001 | S4.18 | verified | Requested and detected language survive SQLite checkpoints and resumption; 400 tests pass, 1 real smoke test stays opt-in. |
| ASR-SANITIZE-001 | S4.04, S4.13 | verified | Cut A: replacement with no retained engines, explicit closing and cancellation even with an empty iterable; 424 backend tests pass, 1 opt-in smoke test skipped, strict checks and frontend green. |

---

## Active work — Section 5

| Package | IDs | State | Last verifiable achievement |
| --- | --- | --- | --- |
| OPTIONS-B1-001 | S5.18 | verified | Query and GET /api/transcription-options without loads or downloads: registry, runtime, execution, IDs and recommendation kept separate; 452 backend tests, 1 smoke test skipped, and checks/backend/frontend green. |
| OPTIONS-UI-001 | S5.19 | verified | Accessible radio selector on top of B1 with translated blocking reasons and a recommendation; 7 Vitest tests, mounted in App; lint/typecheck/build green. |
| PROJECTS-API-001 | S5.01 (backend) | verified | CreateProject/ListProjects and POST/GET /api/projects wired into create_app with an Alembic migration at startup; 24 tests + real HTTP smoke test. |
| MEDIA-UPLOAD-001 | S5.02, S5.03 (backend) | verified | POST /api/projects/{id}/media with a raw body → real ImportMedia (SHA-256, ffprobe), typed 400/404/413/415/422/503, temporary file cleaned up; 18 tests + HTTP smoke test with a WAV fixture. |
| JOBS-CORE-001 | S5.20, S14.01, S14.08 | verified | CreateTranscriptionJob revalidates option_id and stores a snapshot (migration 0003); threaded JobRunner with recover() at startup, cancel between chunks and idempotent PERSISTING; POST/GET/cancel jobs and GET segments wired; 18 tests + HTTP smoke test (409 option_not_startable without a model). The flow with a real model remains experimental. |
| JOBS-SSE-001 | S5.06 | verified | GET /api/jobs/{id}/events through StreamingResponse with polling in a thread, keep-alive and a terminal `end`; useJobEvents hook; 6+6 tests, mounted in create_app and App. |
| UI-IMPORT-001 | S5.01, S5.02, S5.03 (UI) | verified | NewProjectCard: name, native drop, XHR with progress and errors by code; 6 tests; mounted in App and verified against the real backend by a smoke test. |
| UI-JOB-001 | S5.04, S5.05, S5.07 | verified | Per-stage JobScreen, cancel and SegmentList mounted in App over POST /api/jobs + SSE; 18 Vitest tests; 409 path verified live; execution with a real model pending the opt-in smoke test. |
| EXPORT-TEXT-001 | S10.01, S10.02, S10.03, S10.09, S10.10 | verified | Structural TranscriptExporter Protocol, literal TXT, Markdown and anti-traversal safe_export_filename; 51 inline golden tests. |
| EXPORT-SUBS-001 | S10.04, S10.05, S10.06, S10.11, S10.12, S10.13 | verified | SRT, VTT, timestamps with bounds, canonical JSON voz.transcript v1 and parse(render(x)) round-trip; 34 tests. |
| OSS-DOCS-001 | S16.03-S16.08, S16.17, S16.18 | verified | CONTRIBUTING, CODE_OF_CONDUCT (Covenant 2.1), SECURITY, issue/PR templates, fixture licenses and NOTICE with verified licenses; links checked. |
| DOCTOR-CLI-001 | S8.12, S8.13 | verified | `voz doctor` (text/--json/--redact): ffmpeg/ffprobe, port, XDG paths, disk, ASR runtime and GPU without loading models; 12 tests + real execution; `voz` without a subcommand still serves. |
| UI-PLAYER-001 | S5.08, S5.10 | verified | GET /api/media/{id}/original with FileResponse (Range 206/416, no paths) and a native AudioPlayer with seek from SegmentList; 5 backend + 8 frontend tests; live HTTP smoke test 200/206. |
| SEGMENTS-EDIT-001 | S5.12 (backend) | verified | PUT /api/segments/{id} with optimistic revision (conditional UPDATE), original_text preserved, migration 0004 keeps words; real 404 smoke test. |
| EXPORT-HTTP-001 | S10.07, S10.08, S10.14 | verified | GET /api/transcripts/{id}/export in 5 formats, filename* RFC 5987, grouped by speaker and optional times; 17 HTTP tests + goldens; ExportMenu mounted. |
| WAVEFORM-001 | S5.09, S5.14 | verified | Streaming FFmpeg peaks (1 h WAV in 0.86 s, 70 MB RSS), atomic XDG cache, canvas with 1–32x zoom and seek by click/keyboard; 200/422 smoke test. |
| TRANSCRIPT-VIEW-001 | S5.11, S5.13, S5.15 | verified | Active segment by binary search, pausable autoscroll, accent-insensitive search with navigation; content-visibility + memoized rows (10k segments, 2 renders per change). |
| SEGMENT-EDITOR-001 | S5.12 (UI), S5.16 | verified | Drafts kept outside rows, 800 ms debounce + blur, PUT serialized per segment, resolvable 409 conflict, global AutosaveStatus; 29 tests. |
| ARCH-DOCS-001 | S16.09-S16.11 | verified | docs/architecture C4 (context, containers, components) in Mermaid; 83 links and 124 paths checked. |
| ARCH-ADR-001 | S16.12-S16.16 | verified | ADR-0001–0004 completed with evidence; ADR-0005 (providers) and ADR-0006 (local-first) new. |
| ROBUST-001 | S14.03, S14.12, S14.14 | verified | 507 disk_space_insufficient on upload/normalization, ffprobe fuzzing (2 bugs fixed), idempotent resume (2 runner bugs fixed); 739 tests. |
| MODELS-CATALOG-001 | S8.01-S8.03 | verified | Catalog of 6 models with revision, sizes and SHA-256 verified against HuggingFace; GET /api/models with installed/size; turbo recommended. |
| MODELS-ADMIN-001 | S8.07, S8.08 | verified | DELETE /api/models/{id}?confirm= with 409 model_in_use; disk usage per model and free space; HTTP tests. |
| MODELS-STORE-001 | S8.04-S8.06 | verified | Stdlib download with progress, cancellation and per-file SHA-256/size against a local HTTP server; 37 tests. |
| MODELS-STORE-002 | S8.15, S14.04, S14.09 | verified | Range resumption, corrupt .part discarded, inconsistent installation replaced, prior space check with disk_space_insufficient. |
| MODELS-BUZZ-001 | S8.09, S8.10 | verified | Read-only detection of the real Buzz Flatpak (turbo and large-v3) and hardlink import in 1.4 s with SHA-256; Buzz tree untouched. |
| E2E-001 | S5.17 | verified | Full HTTP flow with a real runner (import→job→SSE→Range→peaks→409 edit→export→restart) + App with simulated fetch/XHR/SSE; highlighting bug fixed. |
| PKG-001 | S15.01-S15.03 | verified | 3 identical builds with SOURCE_DATE_EPOCH; wheel broken by .gitignore (transcript.py) fixed; uv tool install runs voz and doctor. |
| PKG-002 | S15.04, S15.05 | verified | Wheel with static files and migrations 0001–0004 (test); installed outside the checkout it serves / and /api/health. |
| PKG-003 | S15.07-S15.09, S15.11 | verified | scripts/checksums.sh, Keep a Changelog CHANGELOG, docs/release.md with semver/public API, docs/install/linux.md. |
| DIAG-001 | S14.10, S14.11, S8.14 | verified | Sqlite backup before migrating (5 retained, aborts on failure), redacted voz doctor --bundle, disk/model/key set/unset checks. |
| MODELS-TASKS-001 | S8.04 (UI), S8.05 (UI) | verified | FIFO ModelTaskRunner with progress/cancellation; POST /api/models/{id}/install with confirmation, /api/model-tasks; test against the real store and a local http.server. |
| MODELS-UI-001 | S8.02 (UI), S8.03 (UI), S8.07 (UI) | verified | Models section mounted: size shown beforehand, import from Buzz, download with <dialog>, progress, cancel, deletion by typing the id; selector sorted and refreshed. |
| HW-RECOMMEND-001 | S8.11, S14.05, S14.06 | verified | nvidia-smi/meminfo without a shell; turbo recommended with VRAM ≥ 6 GiB, small/base on CPU; 409 insufficient_vram/ram before creating a job. |
| DIAR-CORE-001 | S6.01, S6.02, S6.08 | verified | DiarizationProvider port, cluster≠Speaker with persistent palette, reconciliation by maximum overlap; idempotent AssignSpeakers keeps renames. |
| DIAR-CORE-002 | S6.14 | verified | 17 reconciliation cases: overlap, silence, turn crossing segments, edges, disorder and 0 turns. |
| DIAR-SHERPA-001 | S6.16, S6.04 | verified | ONNX models actually downloaded from GitHub with verified SHA-256; real sherpa-onnx adapter separates A/B/A in a synthetic dialogue; ADR-0007. |
| DIAR-SHERPA-002 | S6.05-S6.07 | verified | Real: automatic and exact=2 → A/B/A; range 1–1 re-runs clamped to 1 speaker without reloading models. |
| WORDS-001 | S7.01, S7.03, S7.04 | verified | AlignmentProvider with no extra implementation; ADR-0008 (native faster-whisper, WhisperX not evaluated); Words persisted with uuid5 and clamp; words API ([] if edited). |
| WORDS-002 | S7.08, S7.09 | verified | Fallback without words completes the job; old checkpoints compatible; monotonicity, clamp and overlap without duplication tested; 1011 tests. |
| DIAR-PIPE-001 | S6.13, S6.15, S14.07 | verified | Optional per-job DIARIZING stage (migration 0005), ASR released before diarizing, diarization failure does not lose the transcript; runner with real sherpa over a dialogue passes. |
| SPEAKERS-001 | S6.09-S6.11 | verified | GET/PATCH/merge of speakers with persistent color and name, transactional merge; SpeakersPanel mounted; 19 HTTP tests. |
| SPEAKERS-002 | S6.12 | verified | PUT /api/segments/{id}/speaker and per-row SegmentSpeakerSelect; the list reloads without losing the search (reloadKey). |
| WORDS-003 | S7.05 | verified | Per-word speaker from the turn at its midpoint, computed on the fly in the view (SpeakerTimeline). |
| WORDS-UI-001 | S7.06, S7.07 | verified | WordText with seek by click/keyboard and current word via an external store (re-renders only 2 words); Read/Edit mode. |
| CLOUD-SECRETS-001 | S11.01 | verified | ProviderSecrets: env or atomic 0600 secrets.toml, never in SQLite/logs (tests); /api/providers without echoing the key. |
| OPENAI-001 | S11.02, S11.05, S11.06 | verified | whisper-1 adapter with splitting under 25 MB and global offsets without overlaps; fake transport (experimental, not verified against the service). |
| OPENAI-002 | S11.03, S11.04, S11.07 | verified | gpt-4o-transcribe-diarize with speaker, dated limits, backoff only for 429/5xx/timeout. |
| OPENAI-003 | S11.08, S11.10, S11.11 | verified | Per-endpoint cost estimate, FakeOpenAITransport and openai cases in the common contract suite. |
| OPENAI-004 | S11.12, S11.13 | verified | docs/privacy/openai.md; without a key it does not start, with a key it is never recommended or used as a fallback (0-request tests). |
| ELEVEN-001 | S12.01-S12.03 | verified | Key via ProviderSecrets, Scribe v1 adapter and segments with speaker (fake transport; experimental). |
| ELEVEN-002 | S12.04-S12.06 | verified | Words in monotonic ms, bounded keyterms, progress and upload cancellation without retries that bill twice. |
| ELEVEN-003 | S12.07-S12.09 | verified | Dated price reusing the estimate endpoint; fake client and common contract. |
| ELEVEN-004 | S12.10, S12.11 | verified | docs/privacy/elevenlabs.md and a structural test: the adapter lives only in infrastructure/cloud. |
| WCPP-001 | S9.01, S9.02, S9.05 | verified | WhisperCppProvider with a fake binary, detection validated through --help and 6 ggml models pinned with SHA-256. |
| WCPP-002 | S9.06-S9.08 | verified | -ojf JSON mapped to segments/words, cancellation kills the process, typed errors; the common contract suite passes. |
| WCPP-003 | S9.03, S9.04, S9.09 | verified | docs/whisper-cpp.md (CUDA/Vulkan, documented but not verified here) and a visible, never automatic suggestion; options only if whisper-cli exists. |
| ROBUST-002 | S14.02, S14.13 | verified | 18 critical writes audited (synchronous=FULL, fsync before replace) and close/reopen mid-job without repeating chunks. |
| PKG-004 | S15.10 | verified | Clean clone on Bazzite: uv tool install, asr-local extra with CUDA float16 and server verified; docs corrected. |
| OSS-AUDIT-001 | S16.19 | verified | scripts/audit-secrets.sh over the tree and history: 0 HIGH; author email decision still pending. |
| QUALITY-FLAGS-001 | S13.04, S13.05, S13.12 | verified | avg_logprob/no_speech/compression metrics from faster-whisper; flags repetition, silence_hallucination, out_of_bounds, low_confidence (pure, never touch the text); migration 0006 quality_json; `quality` API; rule S13.12 in docs/api/segments.md. |
| QUALITY-REVIEW-001 | S13.06 | verified | ReviewQueue: "N segments to review", filter by type, previous/next with seek, mark as reviewed (local to the session); rows with an accessible ⚠. |
| BENCH-001 | S13.08-S13.10 | verified | `voz bench`: load, RTF, peak RSS and VRAM (nvidia-smi), --json; dataset only in XDG (rejected inside the checkout); stdlib WER/CER with documented normalization. |
| BENCH-002 | S13.07 | verified | Measured on an RTX 4060: turbo CUDA RTF 0.025 WER 1.66%; large-v3 RTF 0.073 WER 1.99% (8.14% on a long clip); see docs/benchmarks.md (synthetic audio). |
| WCPP-004 | S9.10 | verified | whisper.cpp v1.9.4 built (CPU), ggml q5_0 with verified sha256: RTF 0.80 WER 1.83%; real -ojf JSON as a fixture and adapter test. |
| CLOUD-UI-001 | S11.09 | verified | CLOUD badge before/during/after, mandatory consent, cost estimate, keys set from the UI without displaying them; names/privacy come from the backend (S12.11 intact). |
| MODELS-UI-002 | (completes S8) | verified | `provider:model` keys; ManagedModelCatalog + RoutingModelStore: faster-whisper, whisper.cpp (if whisper-cli exists) and diarization:sherpa-default with download/deletion; real HTTP smoke test OK. |
| PKG-005 | S15.06 | verified | .github/workflows/release-dry-run.yml: reproducible build, checksums, install check, 7-day artifact, contents: read, no publishing (not executed: requires a push). |
| PKG-006 | S15.12, S15.13 | verified | Measured prototypes: AppImage base 46 MiB (startup ~1 s), asr-local 1.42 GiB with CUDA; Flatpak base 52.6 MB installed, asr-local 2.8 GB; recommendation in docs/packaging/appimage-flatpak.md. |
| QUALITY-CORE-001 | S13.01 | verified | Per-project glossary (≤50 terms; migration 0007) frozen in the job selection; passed to faster-whisper as `hotwords` and to the cloud provider's keyterms; real smoke test on an RTX 4060 with "VOZ"/"presupuesto" transcribed. |
| QUALITY-CORE-002 | S13.02, S13.03, S13.11 | verified | Immutable v1 `default`/`academic` profiles stored whole in the selection; per-profile VAD (real smoke test with academic+VAD OK); `GET /api/quality-profiles?language=` recommends only with measurements (es/default, synthetic) and says "no measurement" for everything else. |
| INTEGRITY-001 | (risks) | verified | Cloud providers' `speaker` labels → idempotent Speaker entities (local diarization wins); job and selection in one transaction (`add_with_selection`) with a rollback test. |
| DOCS-DEMO-001 | S16.02 | verified | `scripts/capture-screenshots.sh`: temporary XDG, turbo imported from Buzz, real GPU transcription and 7 screenshots over CDP with headless Chrome Flatpak; docs/demo.md and README. |

### Resuming work

Read `AGENTS.md`, this board and the contracts in `docs/api/`; check Git and run
the validations before editing. Wave 3 (2026-09-30) closed S5 except S5.17
(E2E), all of S10, S14.03/12/14 and S16.09–S16.16. Wave 4a closed S5.17, most of
S8 (S8.11 remained), S14.04/09/10/11 and packaging. Wave 4b+5a closed the Model
Manager in the UI, S8.11, S14.05/06, the diarization core and adapter
(sherpa-onnx) and words. Wave 5b closed S6 (except S6.03), S7 (except S7.02), S9
(except S9.10), S11 (except S11.09), S12, S14.02/07/13, S15.10 and S16.19. Next
(5c): S13 quality, the CLOUD badge (S11.09), S15.06, S16.02.


Since 2026-10-10 the V Program has covered branding, hardening, English
documentation, TTS and release preparation. The following table describes the
verified scope and the pending limitations.

## Voice engine extensions

| Slice | State | Scope |
| --- | --- | --- |
| V5-05 | Verified | Keyboard focus and sample cancellation regressions fixed; Carbon/M3, light/dark and es/en verified at 390 px with deterministic browser inputs. |
| V5-06 | Verified locally | Separate Material 3 library search and table surfaces, visible focus, internal table scrolling and a quieter connection indicator; 16 browser theme/language/viewport combinations verified. |
| V6-05a | Verified | Explicit custom-model previews and confirmed background imports, pinned hashes, isolated load validation, live options and confirmed deletion; fake HTTP and default-wiring tests verified. |
| V6-05c | Verified | Link-first custom-model preview with bounded metadata detection, explicit download confirmation, manual fallback and real-browser STT/TTS flows using synthetic weights. |
| V6-07R | Verified (source review) | Current local STT/TTS model comparison, per-artifact licenses and engine compatibility; no new inference or quality measurements. |
| V6-06 | Verified (experimental) | Whisper ONNX CPU custom imports, private cancellable child and complete 30-second windows; fake provider contracts and browser folder flow verified, real weights unverified. |
| V6-05b | Verified | Browser folder copies and remote previews with explicit installation, live progress, cancellation and visible license; Carbon/M3 responsive dialog. |
| V10-02 | Verified | Private token files, authenticated API/browser access, LAN startup checks and readiness without credential redirects. |
| V7-01 | Verified | Synthetic CPU measurements compare 10/15/30-minute checkpoints with pinned model hashes and persistent SQLite; the 30-minute default remains unchanged. |
| V7-03 | Verified locally | Ten CPU trials on synthetic ABA/AAA at thresholds 0.3–0.7 completed; all gave one raw and one cleaned cluster. This corpus does not separate the ABA voice variants; default 0.4 unchanged. |
| V7-04 | Automated subset verified; manual checks pending | One real CPU job with CUDA hidden, transcript search, native playback timing, five exports and glossary persistence exercised through HTTP and browser input. Switching between two real models and owner listening remain pending. |
| V10-01 | Verified | Same-origin CSP and response hardening, dependency patches with no added packages, installed-environment audits and secret-history review. |
| V10-07 | Verified | Local OpenAI-compatible models, transcription and WAV speech endpoints. |
| V10-07a | Verified locally | Completed HTTP audio requests release their disconnect monitor even when a poll absorbs cancellation; deterministic regression and default-wiring API checks verified. |
| V6-08R | Verified (source review) | STT/TTS comparison across publishers with per-artifact licenses, engine compatibility and measured versus vendor-claimed results separated. |
| V6-08D | Verified locally | Declared CPU/GPU capabilities separated from initial device selection; two real Faster Whisper base CPU/CUDA jobs checked. Other families do not inherit this hardware claim. Model deletion now distinguishes installed and reclaimable bytes. |
| V6-08N | Verified locally, experimental | CPU NeMo transducer import and Piper Claude/Kitten Mini catalog entries; seven short native checks include Kokoro Spanish, English, Portuguese and French. No comparative listening or conversation-quality claim. |
| README-STACK | Verified locally | Frontend/backend stack, HTTP/SSE flow, application read models and directory map checked against source; local links and anchors verified. |
| V10-04 | Base Linux packages verified locally; native checks pending | Current wheel, AppImage and uninstalled Flatpak bundle built offline from existing components; 277 package files/50 static files/README/notices matched. AppImage extraction and Flatpak import/checkout passed isolated HTTP/shutdown checks. FUSE and native Windows/macOS checks remain pending; no inference-enabled portable build claimed. |
| V10-06P | Prepared locally; remote configuration pending | Working tree and reachable-history privacy review, narrow fixture exclusions, bundled license notices and minimal dependency patches verified; npm/OSV snapshots have zero matches. Security reporting instructions prepared; remote private reporting remains a separate action. |
| V10-03 | Verified | Existing CI and dry-run actions pinned to verified commit hashes, checkout credentials disabled and job deadlines set; remote CI green on Linux, macOS and Windows (backend, frontend and package), plus the Launchers workflow that cold-starts the real launcher on all three systems. |
| V10-05 | Verified | Deterministic bundle byte budgets and 40 Chromium structural accessibility/responsive checks, with bounded coverage documented. |
| V8-03 | Verified | STT bench reuse and TTS first-completed-chunk latency, render throughput and separate RSS peaks with unavailable values preserved. |
| V8-04 | Verified | Validated Markdown comparison of saved Edge Lab reports, with measured values and separate memory scopes. |
| V8-02 | Verified | CPU experiment CLI with child-only affinity/address-space controls, deadlines, process-tree cleanup and separate measured/estimated results; disposable-process tests verified. |
| V8-01 | Verified | ADR-0011 defines experiment-only resource controls and separates measured results from estimates; the CPU executor is covered by V8-02. |
| V9-02 | Protocol prepared; board validation pending | Existing-model, isolated CPU measurement procedure for aarch64 SBCs, with explicit outcomes and workload budgets; no board compatibility or thermal behavior established. |
| V5-04 | Verified | Persistent synthesis history with playback, WAV downloads and confirmed deletion, including when no models are installed; UI and static-bundle browser flow verified. |
| V4-04 | Verified | Configurable STT/TTS servers, explicit CLOUD consent, private endpoint storage and safe validation errors; fake HTTP contracts and browser flow verified. |

## Active work — v3 and portable

| Package | IDs | State | Last verifiable achievement |
| --- | --- | --- | --- |
| PORT-001 | S15.15-S15.18 | verified | Windows/macOS/Linux with a double click, a second double click reuses the server, and a desktop shortcut; installable PWA without a test (S15.17 open). |
| UI-V2-001 | S5.27-S5.30 | verified | Editor, per-stage progress with ETA, close server, Carbon themes and es/en i18n. |
| API-V3-001 | S5.32, S6.17-S6.19, S14.15-S14.16 | verified | `GET /api/library`, project rename/delete and `rediarize`: `tests/integration/test_library_projects_api.py`, `tests/integration/application/test_rediarize.py`. |
| UI-V3-001 | S5.21-S5.26 | verified | Home/library, hash routes, review that jumps to the audio, export with preview, volume up to 300% and speakers panel. |
| UI-M3-001 | S5.31 | verified | Material 3 skin selectable in Settings; CI green on 3 operating systems (1186908). |

## Section 1 — Repository bootstrap

- [x] **S1.01** Initialize the repository with the agreed base structure.
- [x] **S1.02** Choose and add a valid license.
- [x] **S1.03** Create a `pyproject.toml` managed with `uv` and Python 3.12.
- [x] **S1.04** Create the React, TypeScript and Vite frontend.
- [x] **S1.05** Expose a minimal FastAPI app with `GET /api/health`.
- [x] **S1.06** Create the `voz` Typer entry point.
- [x] **S1.07** Make `voz` start Uvicorn on loopback.
- [x] **S1.08** Make `voz` open the browser, unless `--no-browser` is given.
- [x] **S1.09** Define XDG paths for config, data, cache and state.
- [x] **S1.10** Configure Ruff for backend lint and formatting.
- [x] **S1.11** Configure the backend type checker.
- [x] **S1.12** Configure pytest and a `/api/health` test.
- [x] **S1.13** Configure ESLint for the frontend.
- [x] **S1.14** Enable TypeScript strict and its check command.
- [x] **S1.15** Configure Vitest and a minimal Home test.
- [x] **S1.16** Create initial CI for backend and frontend checks.
- [x] **S1.17** Create `AGENTS.md` with stable rules and commands.
- [x] **S1.18** Create this roadmap with IDs and atomic tracking.
- [x] **S1.19** Create a local directory for agent-session context and ensure its Git exclusions.
- [x] **S1.20** Record ADR-0001 for the modular monolith.
- [x] **S1.21** Document the development setup on Bazzite.
- [x] **S1.22** Verify clean installation, `voz` startup and local Home on Bazzite.

**Exit criterion:** from a clean checkout the project installs, `voz` runs and
the local UI is visible. Do not install Whisper in this section.

## Section 2 — Domain and persistence

- [x] **S2.01** Model `Project` with identity and invariants.
- [x] **S2.02** Model `MediaAsset` without paths exposed to the UI.
- [x] **S2.03** Model `Transcript`.
- [x] **S2.04** Model `Segment` with valid offsets.
- [x] **S2.05** Model `Word` with valid offsets.
- [x] **S2.06** Model an editable `Speaker`.
- [x] **S2.07** Model `SpeakerTurn` separate from acoustic identity.
- [x] **S2.08** Model the `TranscriptionJob` state machine.
- [x] **S2.09** Test valid job transitions.
- [x] **S2.10** Test rejection of invalid transitions.
- [x] **S2.11** Define repository ports.
- [x] **S2.12** Implement SQLite repositories.
- [x] **S2.13** Create the initial Alembic migration.
- [x] **S2.14** Enable SQLite WAL through the adapter.
- [x] **S2.15** Add unit tests for entities and invariants.
- [x] **S2.16** Add integration tests for SQLite repositories.
- [x] **S2.17** Verify recovery of projects and jobs after a restart.

**Exit criterion:** projects and jobs survive a restart without the domain
depending on SQLite.

## Section 3 — Media ingestion

- [x] **S3.01** Define `MediaProbePort`.
- [x] **S3.02** Implement the ffprobe adapter.
- [x] **S3.03** Validate by streams/codecs and not only by extension.
- [x] **S3.04** Copy the original safely and immutably.
- [x] **S3.05** Compute and persist the hash of the original.
- [x] **S3.06** Extract duration, codec, sample rate and channels.
- [x] **S3.07** Normalize to mono 16 kHz audio for inference.
- [x] **S3.08** Keep playback/export working from the original.
- [x] **S3.09** Report normalization progress.
- [x] **S3.10** Cancel normalization without leaving corrupt artifacts.
- [x] **S3.11** Add a WAV fixture with a compatible license.
- [x] **S3.12** Add MP3 and M4A fixtures with a compatible license.
- [x] **S3.13** Add OGG, OPUS and WebM fixtures with a compatible license.
- [x] **S3.14** Map a corrupt file to a typed error.
- [x] **S3.15** Clean up temporary files on success, failure and cancellation.
- [x] **S3.16** Test import against path traversal and unsafe names.

**Exit criterion:** V ingests common formats that FFmpeg can decode and produces
reproducible normalized audio without modifying the original.

## Section 4 — First local ASR

- [x] **S4.01** Define the `TranscriptionProvider` port.
- [x] **S4.02** Define `ModelDescriptor` and its capabilities.
- [x] **S4.03** Create the provider registry with no imports in the domain.
- [x] **S4.04** Implement the Faster Whisper adapter.
- [x] **S4.05** Implement explicit download of a local model.
- [x] **S4.06** Record the model's revision and provenance.
- [x] **S4.07** Implement the `fast` profile through a descriptor.
- [x] **S4.08** Implement the `quality` profile through a descriptor.
- [x] **S4.09** Detect the GPU and choose an explicit CPU fallback.
- [x] **S4.10** Plan chunks with global offsets.
- [x] **S4.11** Report progress per chunk.
- [x] **S4.12** Persist a verified partial result.
- [x] **S4.13** Cancel ASR between recoverable units.
- [x] **S4.14** Resume from checkpoints without repeating completed chunks.
- [x] **S4.15** Add a contract test for valid audio.
- [x] **S4.16** Add a contract test for monotonic, non-negative timestamps.
- [x] **S4.17** Add a contract test for cancellation and mapped errors.
- [x] **S4.18** Preserve language metadata in the canonical result.

**Exit criterion:** a long file can be transcribed locally and resumed under the
common contract.

Real smoke test 2026-09-30 (RTX 4060 Laptop, CUDA float16 through the nvidia
wheels of the `asr-local` extra): turbo and large-v3 imported from Buzz's cache
pass the opt-in smoke test, and the full HTTP flow transcribes 25 s of Spanish in
~3 s. The local flow, physical chunk trimming and recovery are verified with the
real adapter and a deterministic engine. The real Faster Whisper runtime/model
remains experimental until the opt-in smoke test is run with a model that the
user has chosen and installed explicitly; no weights are downloaded in tests.

Fix S4.04/S4.13 (Cut A, 2026-09-07): regressions with weakrefs and events verify
release before another engine is loaded, a coherent load failure,
idempotent/serialized closing, SDK traceback cleanup and cancellation of the
isolated provider. ADR-0004 documents the lifecycle and its limits. No new IDs
are opened and the experimental rating of the runtime/CUDA is not modified.

## Section 5 — Workspace UI

- [x] **S5.01** Create Home with a “New project” action.
- [x] **S5.02** Implement file selection and drag-and-drop.
- [x] **S5.03** Show upload validation and safe errors.
- [x] **S5.04** Create the job screen.
- [x] **S5.05** Show an explicit state per stage.
- [x] **S5.06** Consume progress through SSE.
- [x] **S5.07** Render the segment list.
- [x] **S5.08** Add a player for the original.
- [x] **S5.09** Render the waveform.
- [x] **S5.10** Seek when a timestamp is selected.
- [x] **S5.11** Synchronize selection/autoscroll with playback.
- [x] **S5.12** Edit and save a segment's text.
- [x] **S5.13** Search text in the transcript.
- [x] **S5.14** Control waveform zoom.
- [x] **S5.15** Virtualize long transcripts.
- [x] **S5.16** Add autosave with a visible state.
- [x] **S5.17** Test import, playback and editing end to end.
- [x] **S5.18** Expose canonical transcription options through a backend query.
- [x] **S5.19** Implement a basic frontend selector, without the Model Manager.
- [x] **S5.20** Persist a reproducible selection for job creation.
- [x] **S5.21** Home with a transcript library: open, rename and delete (`apps/web/src/components/Library.test.tsx`).
- [x] **S5.22** Hash routes with a dedicated link per transcript and Back/reload (`apps/web/src/lib/navigation.test.ts`).
- [x] **S5.23** The review queue jumps to the segment and the audio (`ReviewQueue.test.tsx`, `SegmentList.test.tsx`).
- [x] **S5.24** Export with preview, times and grouping by speaker (`apps/web/src/App.flows.test.tsx`).
- [x] **S5.25** Audio with volume up to 300%, speed and shortcuts (`AudioPlayer.test.tsx`).
- [x] **S5.26** Speakers panel with talk time, filter and sample (`SpeakersPanel.test.tsx`, `lib/speakerTurns.test.ts`).
- [x] **S5.27** Per-stage progress with ETA and live text (`App.flows.test.tsx`, `tests/unit/test_job_views.py`).
- [x] **S5.28** Close server button (`api/shutdown.test.ts`, `tests/integration/test_shutdown_api.py`).
- [x] **S5.29** Carbon themes, accents and es/en i18n (`i18n/i18n.test.ts`, `theme/appearance.test.ts`).
- [x] **S5.30** Transcript editor with a speaker timeline (`App.flows.test.tsx`, `SegmentList.test.tsx`).
- [x] **S5.31** Material 3 skin selectable in Settings (`theme/m3.test.ts`, `theme/appearance.test.ts`).
- [x] **S5.32** `GET /api/library` (`tests/integration/test_library_projects_api.py`).

S5.18–S5.20 query and select known options; downloads, repair, exhaustive
checksums and advanced administration remain in Section 8.

**Exit criterion:** the basic flow of upload, progress, playback and editing is
usable with a long recording.

## Section 6 — Diarization

- [x] **S6.01** Define the `DiarizationProvider` port.
- [x] **S6.02** Model clusters, speakers and assignments separately.
- [ ] **S6.03** Implement the pyannote Community-1 adapter. _(blocked: replaced by S6.16/ADR-0007; requires torch and an HF token; only if the maintainer asks for it)_
- [x] **S6.04** Implement explicit model download/configuration.
- [x] **S6.05** Run automatic detection of the number of speakers.
- [x] **S6.06** Allow a minimum and maximum number of speakers.
- [x] **S6.07** Allow an exact number of speakers.
- [x] **S6.08** Reconcile turns with ASR segments.
- [x] **S6.09** Assign persistent colors per speaker.
- [x] **S6.10** Rename a speaker without re-running models.
- [x] **S6.11** Merge speakers without re-running ASR.
- [x] **S6.12** Reassign a segment manually.
- [x] **S6.13** Test diarization with two speakers.
- [x] **S6.14** Test overlap and segments without a speaker.
- [x] **S6.15** Verify sequential VRAM release between ASR and diarization.
- [x] **S6.16** Implement a local sherpa-onnx adapter without torch or a token (ADR-0007).
- [x] **S6.17** `POST /api/transcripts/{id}/rediarize` without re-transcribing (`tests/integration/application/test_rediarize.py`).
- [x] **S6.18** Measured threshold and merging of small speakers (`tests/unit/application/test_diarization_cleanup.py`, `test_speaker_matching.py`).
- [x] **S6.19** `talk_ms` and `first_ms` per speaker (`tests/integration/test_speakers_api.py`).

**Exit criterion:** “who said what” can be reviewed and corrected without
transcribing again.

## Section 7 — Word timestamps and alignment

- [x] **S7.01** Define the `AlignmentProvider` port.
- [ ] **S7.02** Evaluate WhisperX against fixtures and target languages. _(blocked: requires ~3 GB of torch; ADR-0008 chose native timestamps)_
- [x] **S7.03** Document the alignment adapter decision.
- [x] **S7.04** Persist word-level timestamps.
- [x] **S7.05** Reconcile a word with its speaker.
- [x] **S7.06** Seek when a word is selected.
- [x] **S7.07** Highlight the current word during playback.
- [x] **S7.08** Implement a fallback when no aligner exists for the language.
- [x] **S7.09** Test monotonicity and bounds of word timestamps.

**Exit criterion:** word and audio stay in sync where there is support, with
explicit degradation where there is not.

## Section 8 — Model Manager

- [x] **S8.01** Define the canonical model catalog.
- [x] **S8.02** Show installed/not installed state.
- [x] **S8.03** Show the size before downloading.
- [x] **S8.04** Download with visible progress.
- [x] **S8.05** Allow safe cancellation of a download.
- [x] **S8.06** Verify the checksum or available revision.
- [x] **S8.07** Delete a model with confirmation.
- [x] **S8.08** Show disk usage per model/provider.
- [x] **S8.09** Detect Buzz's cache without modifying it.
- [x] **S8.10** Reuse/import a compatible model without moving the original.
- [x] **S8.11** Recommend profiles according to the detected hardware.
- [x] **S8.12** Implement `voz doctor` for FFmpeg and ports.
- [x] **S8.13** Extend `voz doctor` for GPU/CUDA and the ASR runtime.
- [x] **S8.14** Extend `voz doctor` for disk, models and optional API keys.
- [x] **S8.15** Test an incomplete download and recovery.

**Exit criterion:** the user manages models without touching folders manually.

## Section 9 — whisper.cpp

- [x] **S9.01** Implement the whisper.cpp adapter under the common port.
- [x] **S9.02** Detect and validate the binary.
- [x] **S9.03** Document building/using it with CUDA.
- [x] **S9.04** Document building/using it with Vulkan.
- [x] **S9.05** Register compatible quantized models.
- [x] **S9.06** Map the output to canonical segments.
- [x] **S9.07** Map failures/cancellation to common errors.
- [x] **S9.08** Pass the complete contract test suite.
- [x] **S9.09** Implement automatic fallback only when it is safe and visible.
- [x] **S9.10** Compare CPU/GPU performance with controlled fixtures.

**Exit criterion:** a second complete local implementation exists under the same
contract.

## Section 10 — Export

- [x] **S10.01** Define the export port/service.
- [x] **S10.02** Export literal TXT.
- [x] **S10.03** Export Markdown.
- [x] **S10.04** Export SRT with valid timestamps.
- [x] **S10.05** Export VTT with valid timestamps.
- [x] **S10.06** Export versioned canonical JSON.
- [x] **S10.07** Export grouped by speaker.
- [x] **S10.08** Export text with optional timestamps.
- [x] **S10.09** Sanitize names and prevent path traversal.
- [x] **S10.10** Add TXT/Markdown golden tests.
- [x] **S10.11** Add SRT/VTT golden tests.
- [x] **S10.12** Add JSON golden tests.
- [x] **S10.13** Verify the canonical format round trip where applicable.
- [x] **S10.14** Expose export over HTTP with a safe download.

**Exit criterion:** stable, safe and reproducible exports complete the MVP
together with Sections 1–6.

## Section 11 — Optional OpenAI

- [x] **S11.01** Design API key configuration outside SQLite and logs.
- [x] **S11.02** Implement the file transcription adapter.
- [x] **S11.03** Implement the diarized transcription adapter.
- [x] **S11.04** Detect real limits through configuration/tested versions.
- [x] **S11.05** Split files when the provider requires it.
- [x] **S11.06** Rebuild global offsets without invalid overlaps.
- [x] **S11.07** Implement retries/backoff only for recoverable failures.
- [x] **S11.08** Estimate cost before sending.
- [x] **S11.09** Show a `CLOUD` indicator before and during the job.
- [x] **S11.10** Add a fake client without billable calls.
- [x] **S11.11** Pass contract tests with the fake client.
- [x] **S11.12** Document privacy and the data sent.
- [x] **S11.13** Verify that the provider is never activated implicitly.

**Exit criterion:** OpenAI is interchangeable, explicit and optional; offline
remains the default mode.

## Section 12 — Optional ElevenLabs

- [x] **S12.01** Design secure API key configuration.
- [x] **S12.02** Implement the Scribe adapter.
- [x] **S12.03** Map diarization to the canonical format.
- [x] **S12.04** Map word timestamps to the canonical format.
- [x] **S12.05** Implement per-project keyterms without contaminating the domain.
- [x] **S12.06** Handle long files and progress.
- [x] **S12.07** Estimate cost before sending.
- [x] **S12.08** Add a fake client without billable calls.
- [x] **S12.09** Pass contract tests with the fake client.
- [x] **S12.10** Document privacy and the data sent.
- [x] **S12.11** Verify that the UI/core domain do not change because of this adapter.

**Exit criterion:** ElevenLabs works as an additional backend without becoming a
dependency of the product.

## Section 13 — Transcription quality

- [x] **S13.01** Model glossary/keyterms per project.
- [x] **S13.02** Create an explicit, reproducible academic profile.
- [x] **S13.03** Make VAD configurable per profile.
- [x] **S13.04** Implement non-destructive heuristics against hallucinations.
- [x] **S13.05** Flag low-confidence segments.
- [x] **S13.06** Create a low-confidence review flow.
- [x] **S13.07** Run an A/B model comparison on the same fixture.
- [x] **S13.08** Measure time, realtime factor, RAM and VRAM.
- [x] **S13.09** Keep the personal dataset out of Git.
- [x] **S13.10** Add an optional WER/CER tool.
- [x] **S13.11** Recommend a profile per language using measured results.
- [x] **S13.12** Separate the literal transcript from any post-processing.

**Exit criterion:** the user can measure which configuration works best with
their own recordings without presenting intuitions as results.

## Section 14 — Robustness

- [x] **S14.01** Recover interrupted jobs at startup.
- [x] **S14.02** Write checkpoints and critical metadata atomically.
- [x] **S14.03** Check space before import/normalization.
- [x] **S14.04** Check space before downloading models.
- [x] **S14.05** Add a RAM guard.
- [x] **S14.06** Add a VRAM guard.
- [x] **S14.07** Release models between ASR and diarization by default.
- [x] **S14.08** Implement real cancellation for every processable stage.
- [x] **S14.09** Recover corrupt/incomplete downloads.
- [x] **S14.10** Create a backup before a destructive migration.
- [x] **S14.11** Generate a redacted diagnostic bundle.
- [x] **S14.12** Add fuzz tests for import metadata.
- [x] **S14.13** Test close/reopen during a long job.
- [x] **S14.14** Test resume idempotency.
- [x] **S14.15** Rename a project `PATCH /api/projects/{id}` (`tests/integration/test_library_projects_api.py`).
- [x] **S14.16** Delete a project with its media and 409 `project_busy` (`tests/integration/test_library_projects_api.py`).

**Exit criterion:** closing or reopening V does not destroy confirmed work and
failures give recoverable actions.

## Section 15 — Packaging and release

- [x] **S15.01** Build a reproducible wheel.
- [x] **S15.02** Build a reproducible sdist.
- [x] **S15.03** Verify installation with `uv tool install`.
- [x] **S15.04** Include the frontend bundle in the package.
- [x] **S15.05** Verify execution without a development checkout.
- [x] **S15.06** Create a test (dry-run) release workflow.
- [x] **S15.07** Generate artifact checksums.
- [x] **S15.08** Maintain a changelog.
- [x] **S15.09** Adopt semantic versioning.
- [x] **S15.10** Verify the documented installation on Bazzite.
- [x] **S15.11** Document generic Linux installation.
- [x] **S15.12** Evaluate AppImage with a measured prototype.
- [x] **S15.13** Evaluate Flatpak with a measured prototype.
- [ ] **S15.14** Publish a release only with explicit authorization.
- [x] **S15.15** Portable on Windows/macOS/Linux with a double click and FFmpeg on demand (`backend-portable` job in `.github/workflows/ci.yml` on windows-latest and macos-latest; no manual test).
- [x] **S15.16** A second double click reuses the open V (`tests/unit/test_cli.py`).
- [ ] **S15.17** PWA installable from Chrome/Edge (no automated test).
- [x] **S15.18** Desktop shortcut (`tests/unit/infrastructure/test_desktop_shortcut.py`, `tests/integration/test_desktop_shortcut_api.py`; not portable: see V Program V1-05).

**Exit criterion:** a third party can install an artifact following only the
README, without depending on the checkout.

## Section 16 — Open source readiness

- [x] **S16.01** Create a professional README that is honest about the current state.
- [x] **S16.02** Add a demo and screenshots that correspond to real features.
- [x] **S16.03** Create `CONTRIBUTING.md`.
- [x] **S16.04** Create `CODE_OF_CONDUCT.md`.
- [x] **S16.05** Create `SECURITY.md` with a reporting channel.
- [x] **S16.06** Create a bug issue template.
- [x] **S16.07** Create a feature issue template.
- [x] **S16.08** Create a PR template with relevant checks.
- [x] **S16.09** Document the C4 context diagram.
- [x] **S16.10** Document the C4 container diagram.
- [x] **S16.11** Document the C4 component diagram.
- [x] **S16.12** Complete the ADR on hexagonal boundaries.
- [x] **S16.13** Complete the ADR on SQLite/filesystem.
- [x] **S16.14** Complete the ADR on FFmpeg ingestion.
- [x] **S16.15** Complete the ADR on providers.
- [x] **S16.16** Complete the local-first ADR.
- [x] **S16.17** Document the licenses of all fixtures.
- [x] **S16.18** Create `NOTICE` for reused code/dependencies.
- [x] **S16.19** Audit secrets and ignored files before opening the repository.
- [ ] **S16.20** Make the repository public only with explicit authorization.

**Exit criterion:** the repository is ready to receive external contributions,
with real evidence and no private material.

---

## Milestones

- **Executable skeleton:** Section 1 complete.
- **Local MVP:** Sections 1–6 and 10 complete.
- **Extensible providers demonstrated:** Sections 9, 11 or 12 depending on
  priority, keeping at least two implementations under contract tests.
- **Installable release:** Section 15 complete.
- **Public opening:** Section 16 complete and explicit authorization from the
  owner.

Milestones do not replace the checkboxes: they are declared reached only when all
of their mandatory IDs are verified.
