# Transcription options — Cut B1 / S5.18

`GET /api/transcription-options` returns HTTP 200 with `{ "options": [...] }`.
OpenAPI (`/openapi.json`, `/docs`) publishes the real schema derived from the
application projections. It takes no parameters and changes no state. Common
rules: [README.md](README.md).

## Semantics

| Field | Meaning and limit |
| --- | --- |
| `provider_id` | Identifier of the known adapter; it does not prove its runtime is installed. |
| `model_id`, `source`, `revision` | Model and pinned provenance. `source` and `revision` are null for a known entry that has no local revision yet. A SHA is never invented. |
| `display_name` | Human-readable model name. |
| `profile` | The full `ProcessingProfile`: name, device preference, ordered GPU precisions and CPU precision. It is not the model nor the chosen execution. |
| `installation_status` | `registered` if a valid V manifest matches identity, canonical location and a time-zone-aware timestamp. `not_registered` if no valid record is found for that known option. An invalid manifest is not the same as the weights being physically absent. |
| `files_available` | Shallow check of `model.bin`, `config.json`, `tokenizer.json` and the vocabulary that corresponds to the model (`vocabulary.txt` in tiny/base/small/medium, `vocabulary.json` in large-v3/turbo): regular, non-empty files, no symlinks. It does not validate content, checksums or integrity. |
| `runtime_available` | The engine class can be imported and the runtime probe answers. No engine is built and no inference runs. |
| `execution` | `ExecutionDecision`: device, precision and fallback_reason, keeping the existing policy. Null if it cannot be selected. |
| `device_name` | GPU name measured with `nvidia-smi` (truncated, printable characters only) when the chosen execution is `cuda`; null on CPU or if there is no measurement. VRAM is never inferred from the marketing name. |
| `capabilities` | Intersection of the descriptor and what the V adapter exposes. CPU/GPU are backends the adapter supports; concrete availability is read from `execution`, not deduced from this list. |
| `can_start` | All observable prerequisites pass: registration, pinned revision, minimum files, runtime, compatible execution and transcription. It allows attempting to load; it **does not guarantee** integrity, enough RAM/VRAM, inference success or real CUDA validation. |
| `recommendation` | `{ "recommended": bool, "reason": str }` or null. **With measured hardware** it is computed by fit to VRAM/RAM (next section), whatever the installation state (only if the sole blockers are installation ones). **Without measurement**: `{ "recommended": true, "reason": "default_compatible_profile" }` for `fast` options that can start; null otherwise. Declarative policy, not a benchmark. There may be several eligible local revisions: which one is newest/best is not invented. |
| `blocking_reasons` | Stable codes; an empty list if `can_start` is true. |
| `cloud`, `provider_label` | `cloud` is true for cloud-provider options; `provider_label` is the provider's display name (null for local options). See [providers.md](providers.md). |

The blocking codes are `model_not_registered`, `model_files_missing`,
`revision_unpinned`, `runtime_unavailable`, `execution_unavailable` and
`transcription_unavailable`. They can coexist. A missing runtime, a missing model
or being unable to recommend are valid responses, not HTTP 500.

If storage cannot be inspected because of an access failure, HTTP 503 is returned
with `detail.code = transcription_options_unavailable` and a safe message. Paths,
manifest contents and tracebacks are never returned.

## Recommendation from measured hardware (S8.11)

The probe measures, without loading any model: the name and total/free VRAM of
the first GPU (`nvidia-smi --query-gpu=name,memory.total,memory.free
--format=csv,noheader,nounits`, no shell, 5 s timeout; only if CUDA is usable)
and total/available RAM (`/proc/meminfo`, Linux only). Any failure means "not
measured" (null), never zero. The pure function
`application/hardware_recommendation.recommend` applies:

| Measured hardware | Recommended option (`reason`) |
| --- | --- |
| CUDA, VRAM >= 6 GiB | `turbo` recommended (`gpu_fast_default`); `large-v3` with `recommended=false` (`gpu_quality_fits`) |
| CUDA, 5 GiB <= VRAM < 6 GiB | `medium` (`gpu_limited_medium`) |
| CUDA, VRAM < 5 GiB | `small` (`gpu_limited_small`) |
| CPU only, RAM >= 8 GiB | `small` (`cpu_default`) |
| CPU only, RAM < 8 GiB | `base` (`cpu_low_ram`) |

The other models get `recommendation = null`. Origin of the policy: the memory
figures published for faster-whisper/CTranslate2 and the times measured on the
target machine (RTX 4060 Laptop, 8188 MiB: turbo fp16 loads in 1.0 s and
transcribes 25 s in 0.9 s; large-v3 in 2.1 s / 1.7 s). It is not an exhaustive V
benchmark. Without measurement the previous behavior is kept.

## Current catalog

The Faster Whisper entries come from `faster_whisper_catalog()` (S8.01): six
Faster Whisper models with pinned source and revision, MIT license, multilingual.

| `model_id` | Profile |
| --- | --- |
| `tiny`, `base`, `small` | `fast` |
| `medium` | `quality` |
| `large-v3` | `quality` |
| `turbo` (large-v3-turbo) | `fast`, the default recommendation |

`/api/transcription-options` exposes one option per entry, installed or not. With
a valid local registration, the registered revisions that match the known source
are exposed (there may be a revision different from the pinned one). Without a
registration the entry is exposed with its pinned revision and `not_registered`;
`revision_unpinned` no longer appears for the current catalog, and `option_id` is
stable because it depends on the pinned revision. No remote catalog or external
cache is queried. Installing, importing and deleting are documented in
[models.md](models.md).

Besides the Faster Whisper entries, the list also contains whisper.cpp options
(only when the `whisper-cli` runtime is available; see
[whisper-cpp.md](../whisper-cpp.md)) and one option per cloud provider
([providers.md](providers.md)).

The current capabilities are `cpu`, `gpu`, `language_detection` and
`transcription`. Although the upstream descriptor mentions translation, the
current port does not allow requesting that task: B1 does not advertise it. It
does not advertise diarization or word_timestamps either.

## Identity and job creation

`option_id` uses the prefix `option-v1-` followed by the SHA-256 of the canonical
JSON of `[provider_id, model_id, source, revision, full_profile]`, with sorted
keys and compact separators. It does not depend on display_name, listing order,
registration or observed hardware. This hash identifies a configuration; **it is
not a checksum of the weights**.

An entry without a revision cannot be submitted as an executable selection (the
current catalog no longer produces any). `POST /api/jobs` revalidates the ID
against the current catalog and pins in the job the full descriptor/profile, the
execution decision and the options that affect the result (for example language)
— see "Reproducible selection" in [jobs.md](jobs.md). The ID alone does not
replace that snapshot.

## Architectural and operational limits

The router receives `GetTranscriptionOptions` from bootstrap, with no disk
inspection or SDK imports. The use case depends on two read-only ports and applies
the policy through `HardwareCapabilities → ExecutionDecision`. The adapters read
registrations and query the runtime. There is no new service locator or mutable
singleton. The synchronous route runs in FastAPI's thread pool, not in the event
loop.

Querying does not download models, load engines or write manifests. The result is
an observation and can go stale; it must be revalidated when a job is created.
The runtime keeps its experimental rating.

This changes no architectural decision of ADR-0001/0004; this document describes
the query contract and introduces no new ADR.
