# Quality profiles, glossary and VAD (S13.01–S13.03, S13.11)

A **profile** is a decoding recipe with a name, a version and fixed parameters.
The job stores the full profile in its selection, so repeating it uses exactly the
same thing even if the bundled recipes change later.

## Bundled profiles

Defined as immutable data in `application/quality_profiles.py` (`QualityProfile`,
`domain/entities/quality_profile.py`). Changing a value requires bumping
`version`.

| Parameter | `default` v1 | `academic` v1 |
| --- | --- | --- |
| `beam_size` | 5 | 5 |
| `temperature` (retries) | 0.0 0.2 0.4 0.6 0.8 1.0 | 0.0 0.2 0.4 |
| `condition_on_previous_text` | yes | **no** |
| `no_speech_threshold` | 0.6 | 0.6 |
| VAD | off | **on** (threshold 0.5; minimum speech 250 ms; minimum silence 1000 ms; padding 400 ms) |

- `default` is Faster Whisper 1.2.1's own defaults: a job with this profile
  behaves as it did before profiles existed (and like `voz bench`).
- `academic` targets long classes and talks: not carrying over the previous text
  keeps a hallucinated or looping sentence from contaminating the next window;
  fewer random retries reduce invented words; VAD skips silence and noise.
  **These choices come from what the library documents, not from a V measurement
  of its own**: `academic` is listed as "unmeasured" until `voz bench` is run with
  it. Do not market it as more accurate.

Without `profile` in the request, `default` is used. Earlier jobs (`NULL` column)
keep the engine's values.

## Who honors what

| Engine | Profile | VAD | Glossary |
| --- | --- | --- | --- |
| Faster Whisper | yes (`beam_size`, `temperature`, `condition_on_previous_text`, `no_speech_threshold`) | yes (`vad_filter` + `vad_parameters`) | yes, via `hotwords` |
| whisper.cpp | ignored | ignored | ignored |
| Cloud (OpenAI) | ignored | ignored | ignored |
| Cloud with *keyterms* (the provider that supports them) | ignored | ignored | yes, as `keyterms` |

The UI says so next to the selector and the editor. The exceptions are recorded in
`applies_to` (`GET .../glossary`).

### Glossary: `hotwords` and not `initial_prompt`

Faster Whisper offers both routes. `hotwords` is used because the library
prepends it to the prompt of **every** decoding window, whereas `initial_prompt`
only seeds the first one, and it also leaves `initial_prompt` free for other uses.
Terms are joined with `", "`. The library truncates on its own if they exceed half
of the context, so very long lists lose the last terms: put the most important
ones first. `hotwords` has no effect when `prefix` is used (V does not use it).
For cloud providers with *keyterms*, each term is sent as a separate field (added
to those the provider already had, respecting its limit of 100 × 50 characters; if
exceeded, the job fails with a typed error, never silently trimmed). **The
transcribed text is never rewritten with the glossary**: it only biases the engine
and the result is stored literally.

Privacy: the glossary travels to a cloud provider only if the user explicitly
chose that provider (the same consent as the audio).

### VAD

`vad_filter`/`vad_parameters` come from the profile (`vad = null` turns it off).
Faster Whisper **ignores VAD when explicit `clip_timestamps` are passed**; V
transcribes each already-trimmed chunk with `clip_timestamps="0"`, so VAD is
applied. The Silero VAD model ships inside the `faster-whisper` package: nothing
is downloaded.

## Reproducibility

`transcription_job_selections.profile_json` stores the full profile (name,
version, parameters and VAD) and `glossary_json` the terms frozen when the job was
created (migration `0007_project_glossary`). The selection is immutable, and
resuming after a restart rebuilds the request from it. `GET /api/jobs/{id}`
exposes `selection.quality_profile` and `selection.glossary`.

## Recommendation by language (S13.11)

`recommend_profile(language)` is a pure function. It only uses the `MEASUREMENTS`
table in `application/quality_profiles.py`, whose rows are numbers that exist in
[benchmarks.md](benchmarks.md). Rule: among the profiles **measured** for the
language (a regional tag reduced to its primary subtag: `es-CO` → `es`) it picks
the one with the lowest WER; if there is no row, it answers `measured: false` and
a "no measurement" message (currently a Spanish string from the API: `sin
medición para el idioma «xx»`, or `sin medición: elige un idioma` when no
language was given), recommending nothing. `unmeasured_profiles` lists the
profiles without a measurement for that language.

Current state of the measurements:

| Language | Profile | WER | Source |
| --- | --- | --- | --- |
| `es` | `default` | 1.66 % | [benchmarks.md](benchmarks.md), 2026-09-30, Faster Whisper turbo CUDA float16, 6 clips of ~36 s |

Limitations that the API repeats in `evidence`/`synthetic`: the audio was
**synthetic** (espeak-ng), so the WER is optimistic and indicative only; only the
`default` profile (the default decoding) was measured, and only Spanish.
`academic` has no measurement in any language. To add a row: run `voz bench` with
the profile and the language, copy the WER into `MEASUREMENTS` with its
provenance and update this table; never estimate.
