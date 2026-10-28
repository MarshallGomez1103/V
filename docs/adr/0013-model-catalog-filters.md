# ADR-0013: Model catalog metadata, filters and the meaning of "best model"

- Status: Proposed
- Date: 2026-10-28
- Owners: V maintainers
- Scope: which facts about a model the catalog exposes, how the Model Manager
  filters and sorts by them, what V is allowed to call the "best" model, and
  whether combining several engines ("super transcription") is adopted. No model
  is added or downloaded by this ADR. Nothing described here exists in the code
  yet; it is **planned**.
- Related: [ADR-0004](0004-local-asr-and-recoverable-chunks.md) (explicit,
  pinned models), [ADR-0005](0005-transcription-providers.md) (providers),
  [ADR-0010](0010-voice-engines-and-tts.md) (engines, capabilities, licensing),
  [ADR-0011](0011-edge-lab.md) (local measurements),
  [local benchmarks](../benchmarks.md)
- Diagrams: [components](../architecture/03-componentes.md)

## Context

The Model Manager lists every installable model (Faster Whisper, whisper.cpp,
diarization, speech synthesis, user-imported) with install state and size.
People now want to narrow that list by language, by CPU or GPU, by size and by
license, and to know which model is best. The facts available today:

- **What the API exposes.** `ModelStatus`
  (`src/voz/application/model_manager.py`, `ModelStatus`) carries identity, `kind`,
  `license` (free text), `multilingual` (a boolean), `capabilities`, the profile
  name (`fast` or `quality`), sizes and install state. There is no language list,
  no device, no quality figure and no source for any of them.
- **The UI has no filters.** `apps/web/src/components/ModelManager.tsx` groups
  models (`modelGroup`) and sorts them (`compareModels`); it filters only by
  runtime availability and provider.
- **CPU and GPU are declared per engine, not per model.**
  `ENGINE_CAPABILITIES` (`src/voz/infrastructure/model_registry.py`) gives
  every Faster Whisper and whisper.cpp model both `cpu` and `gpu`. whisper.cpp
  declares `gpu` although its profile is CPU only
  (`src/voz/infrastructure/asr/whisper_cpp_catalog.py`). A filter on
  `capabilities` for "GPU only" would return no model, and "CPU" would return
  all of them. The signal that distinguishes models is `device_preference` of the
  `ProcessingProfile` (`src/voz/domain/entities/processing_profile.py`, `DevicePreference`),
  which the API does not expose today.
- **Languages.** Speech synthesis entries list languages
  (`TtsModelEntry.languages`, `src/voz/infrastructure/tts/catalog.py`) but
  `ManagedModel.multilingual` is only `len(languages) > 1`
  (`src/voz/infrastructure/model_registry.py`). Whisper entries say
  `multilingual=True` without a list.
- **Identity must not change.** The model descriptor is persisted in each job's
  selection snapshot (`model_json`,
  `src/voz/infrastructure/persistence/schema.py`), so adding presentation facts
  to `ModelDescriptor` would alter stored identities.
- **Quality figures are rare.** The Whisper paper (arXiv 2212.04356, table 13)
  reports word error rate (WER) on FLEURS Spanish for `tiny` through `large`
  models; NVIDIA's model card for Parakeet TDT 0.6B v3 reports one figure for the
  same benchmark. No primary source gives a Spanish FLEURS figure for
  `large-v3` or `turbo`, which V ships. V measures its own models with
  `v bench` (`src/voz/interfaces/cli/bench.py`) and Edge Lab, but those results
  are written outside the repository and no API reads them.

## Decision

### 1. Facts live in the catalog entry, not in the descriptor

`ModelDescriptor` stays as it is. The facts are added to the catalog entry that
the Model Manager already reads (`ManagedModel`,
`src/voz/infrastructure/model_registry.py`, `ManagedModel`) and exposed in `ModelStatus` and
`GET /api/models` as **additive** fields:

| Field | Type | Source and rule |
| --- | --- | --- |
| `languages` | list of ISO 639-1 codes | Declared per entry. For speech synthesis it is the existing `languages`. For a multilingual ASR model with no per-language list it is empty and `multilingual` stays `true`. Empty and not multilingual means unknown. |
| `device` | `cpu_only` or `gpu_preferred` | Derived from `profile.device_preference`. An entry without a profile (diarization, speech synthesis) is `cpu_only`, matching its engine capabilities. Every `gpu_preferred` model also runs on CPU. |
| `license_id` | SPDX identifier or `null` | Set only when one SPDX identifier describes the model's weights. The free-text `license` stays displayed unchanged. V does not classify "commercial use allowed". |
| `ram_bytes` | integer or `null` | Only where a measured peak exists (speech synthesis entries have `ram_bytes` today). `null` otherwise. No VRAM figure is added: the measured values live in documentation, not in the catalog. |
| `published_quality` | list of figures | Each figure: `metric` (`wer`), `value` (fraction), `dataset`, `language`, `source_url` (https), `note` (normalization or caveat). Added by hand with a source that was read; the list is empty when there is none. |

`ENGINE_CAPABILITIES` is **not changed** by this ADR: its values are persisted
and serialized and are documented as "only add". The mismatch for whisper.cpp
is recorded as a follow-up fix.

The initial `published_quality` content is limited to figures with a primary
source: Whisper `tiny` 15.9 %, `base` 9.9 %, `small` 5.6 % and `medium` 3.6 % on
FLEURS Spanish (arXiv 2212.04356, table 13). The figures describe the upstream
model, not V's quantized CPU runtime, and say so in `note`. `large-v3`, `turbo`
and the whisper.cpp quantizations get **no figure** until a primary source or a
local benchmark provides one.

### 2. Filters run in the browser

`GET /api/models` already returns the whole catalog with install state, there is
no pagination, and the list is a few dozen rows. Filtering and sorting are pure
functions of the fields above, so they run in the client. A server-side query
API would add a contract, parameters and tests for no gain. If the catalog ever
reaches thousands of entries, replace this decision.

Filters in the Model Manager:

- text search over name, model id and source;
- task (`kind`): transcription, speech synthesis, speaker separation;
- language: matches entries that **list** the language, and, shown as a weaker
  match, multilingual entries that do not list it ("multilingual, not verified
  for this language");
- runs on: "CPU" (every model), "GPU-accelerated" (`gpu_preferred`) and "CPU
  only" (`cpu_only`). The word "only" is kept for CPU because no model is GPU
  only;
- maximum download size;
- installed only;
- license identifier (options built from the values present);
- sort by name, size or published figure.

Behaviour: filters combine with AND; a visible "N of M models" count is
announced to assistive technology when it changes; an empty result shows a
message and a "clear filters" action; each control has a label and works with
the keyboard; all texts are in the English and Spanish catalogs.

### 3. What "best model" means in V

V does not publish a global ranking. The interface offers three things and names
each one for what it is:

1. **Recommended for this machine.** The existing hardware-aware
   recommendation (`src/voz/application/hardware_recommendation.py`) stays,
   with its reason shown. It is about fit (memory, GPU), not accuracy.
2. **Lowest published error rate for a chosen benchmark.** Sorting by
   `published_quality` requires choosing one `(dataset, language)` pair; models
   without a figure for it sort last and are labelled "no published figure".
   Every figure is shown with its dataset, language and a link to its source.
   Figures from different sources and normalizations are never merged into one
   ranking.
3. **Measured on this machine.** Real-time factor, memory and error rate from
   `v bench` or Edge Lab ([benchmarks](../benchmarks.md)). **Deferred:** it needs
   a decision on where local results are stored and how the API reads them.
   Until then the column does not exist, and the word "best" does not appear in
   the interface or the documentation.

No error rate is estimated, interpolated or inferred from a model's size.

### 4. "Super transcription" is deferred, not adopted

The idea is to combine several models to improve the transcript. Three designs
were evaluated:

- **Word voting (ROVER-style).** Align the word sequences of several engines
  and vote per position. Cost: every engine runs on the whole recording, one
  after another, because a single compute slot serializes heavy work
  (`src/voz/application/compute_slot.py`, `ComputeSlot`); and it needs word timings, which
  Parakeet through sherpa-onnx does not provide
  ([sherpa-onnx ASR](../sherpa-onnx-asr.md)).
- **Confidence cascade.** Transcribe with a fast model, then re-run only the
  low-confidence segments with a larger one. The signal already exists for the
  Whisper family: `Segment.avg_logprob` and the `low_confidence` flag
  (`src/voz/domain/entities/segment.py`, `src/voz/application/quality_flags.py`).
  It is not available for sherpa-onnx engines, so the cascade would be limited
  to Whisper-family models.
- **Two-engine agreement** with a tie-break. Always two full passes, and there is
  no verified tie-break across engine families.

Correcting text with a language model is excluded by the rule in
[AGENTS.md](../../AGENTS.md): a literal transcript is not silently replaced by
LLM output.

**Decision: defer.** Reasons:

- there is no measurement that any combination beats the best single model on V's
  models, and the extra processing time is certain;
- the stored transcript does not record which engine produced which segment, so a
  merged result could not be traced back, which conflicts with keeping the
  transcript literal;
- the confidence signal is engine-specific.

**Revisit when** a local benchmark on a Spanish corpus approved by the maintainers
shows that the cascade beats the best single model by a margin they set,
at an acceptable time cost. Two prerequisites would be built first: per-segment
provenance (engine and model) and the benchmark itself. The verification
findings of [ADR-0014](0014-mcp-and-transcript-verification.md) could then select
the segments to re-run.

### 5. Candidate models

Adding a model to the catalog is a separate decision with its own review:
pinned revision or release, checksum, license read in the source, and
maintainer approval before any download (rule in
[ADR-0004](0004-local-asr-and-recoverable-chunks.md)). This ADR only records what
was found, with sources read on 2026-10-28.

Already in the catalog and relevant to Spanish: Whisper `tiny`, `base`, `small`,
`medium`, `large-v3` and `turbo` (Faster Whisper); the six whisper.cpp
quantizations; Piper `es_MX-ald-medium`, `es_MX-claude-high` (int8) and
`es_ES-davefx-medium`; Kokoro multi-language v1.0, which includes three Spanish
voices.

Not in the catalog:

| Candidate | Task | License (source) | Fit with V |
| --- | --- | --- | --- |
| NVIDIA Parakeet TDT 0.6B v3 | Transcription, Spanish among 25 languages; FLEURS Spanish 3.45 % | CC-BY-4.0 ([model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)) | Importable today through the experimental sherpa-onnx `nemo_transducer` family; no aligned words; no confidence signal. |
| Whisper large-v2 | Transcription; FLEURS Spanish 3.0 % | MIT ([repository](https://github.com/openai/whisper)) | Same engine as the catalog; the CTranslate2 conversion has not been checked. |
| NVIDIA Canary 1B v2 | Transcription, 25 languages | CC-BY-4.0 ([model card](https://huggingface.co/nvidia/canary-1b-v2)) | Needs a new engine family; no Spanish-only figure found. |
| Qwen3-ASR 1.7B | Transcription, Spanish included | Apache-2.0 ([model card](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)) | Needs a new engine family; no Spanish figure found. |
| Piper `es_AR-daniela-high` | Speech synthesis | CC-BY-SA 4.0 ([model card](https://huggingface.co/rhasspy/piper-voices/raw/main/es/es_AR/daniela/high/MODEL_CARD)) | Same family as existing voices; share-alike terms; presence in the sherpa-onnx releases not checked. |
| Piper `es_ES-sharvard-medium` | Speech synthesis | CC BY 3.0 ([model card](https://huggingface.co/rhasspy/piper-voices/raw/main/es/es_ES/sharvard/medium/MODEL_CARD)) | Same family; attribution required; release presence not checked. |
| Supertonic 3 | Speech synthesis, 31 languages | OpenRAIL-M weights ([model card](https://huggingface.co/Supertone/supertonic-3)) | Needs a new family; use restrictions to be read. |
| KittenTTS 2 | Speech synthesis, Spanish included | Stellon Labs Community License ([model card](https://huggingface.co/KittenML/kitten-tts-2)) | Commercial use is free only below a revenue or funding threshold; sherpa-onnx does not document it; **a licensing decision is required**; not a downloadable candidate. |

Notes on the data: the Kitten models V integrates (`nano` and `mini`
0.8) speak English only; no GPU-only model exists; and the official sherpa-onnx
model pages list no Spanish streaming recognizer, which matters to any future
live-transcription decision.

## Positive consequences

- "Spanish", "runs on CPU" and "small enough" become answerable from data that
  is already in the catalog or has a named source.
- Identity and stored job snapshots are untouched.
- The interface cannot claim a winner the data does not support.
- No server query surface and no new dependency.

## Costs and limits

- Someone must read a source and maintain `published_quality`; most models will
  show no figure.
- Multilingual Whisper entries match any language only as a weak match.
- `license_id` covers single-license models; compound licenses (a model plus an
  espeak-ng component) stay as text.
- Published figures are for upstream models; V's quantized CPU runs may differ.
- The whisper.cpp `gpu` capability stays inconsistent with its profile until
  fixed separately.
- Without local results, the interface cannot say which model is faster on a
  particular machine.

## Alternatives considered

### Put the facts in `ModelDescriptor`

Rejected: the descriptor is persisted in job snapshots, and facts such as
quality figures change without the model's identity changing.

### Filter on the server (`GET /api/models?language=es&device=cpu`)

Rejected: the full list is small, already returned, and the filters are pure
functions of it.

### Filter by `capabilities` for CPU and GPU

Rejected: capabilities are declared per engine; see Context.

### One "quality score" per model

Rejected: figures from different datasets, languages and normalizations do not
form one number, and V has no data for several of its own models.

### Adopt a super-transcription mode now

Rejected for now; see section 4.

### Rank candidates by a size heuristic

Rejected: size does not predict word error rate across families.

## Current evidence (2026-10-28)

| Requirement | Code or source |
| --- | --- |
| API fields and catalog entry | `src/voz/application/model_manager.py` (`ModelStatus`), `src/voz/infrastructure/model_registry.py` (`ManagedModel`) |
| Capabilities by engine | `src/voz/infrastructure/model_registry.py` (`ENGINE_CAPABILITIES`) |
| Device preference in the profile | `src/voz/domain/entities/processing_profile.py` (`DevicePreference`) |
| TTS languages and measured RAM | `src/voz/infrastructure/tts/catalog.py` (`TtsModelEntry`) |
| UI without filters | `apps/web/src/components/ModelManager.tsx` |
| Hardware-aware recommendation | `src/voz/application/hardware_recommendation.py` |
| Confidence signal on segments | `src/voz/domain/entities/segment.py`, `src/voz/application/quality_flags.py` |
| Whisper FLEURS Spanish figures | arXiv 2212.04356, table 13 |
| Parakeet FLEURS Spanish figure | model card linked above |
| Filters, new fields, figures | **planned** |

## Verification

This decision is respected when:

- `GET /api/models` returns the new fields for every catalog entry, and a test
  fails if a `published_quality` figure lacks an https source, a dataset or a
  language;
- a test shows that no model is classified as GPU only and that "CPU only"
  excludes every `gpu_preferred` model;
- the filter functions are tested with fixture data and no network access;
- the Model Manager can be filtered, searched and sorted with the keyboard in
  English and Spanish, and the result count is announced;
- the words "best" and "recommended" appear only with the qualifiers in
  section 3;
- no figure in the catalog comes from a source that was not read.

**Review criterion:** replace the deferral in section 4 when a measured benefit
and per-segment provenance exist; replace section 2 if the catalog outgrows a
single response.
