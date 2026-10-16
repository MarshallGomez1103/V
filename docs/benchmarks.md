# Local benchmarks (`voz bench`)

Measures time, real-time factor (RTF), memory and, when a reference exists,
WER/CER of an **already installed** model. Roadmap section 13 (S13.07–S13.10) and
S9.10. Nothing is downloaded, nothing leaves the machine, and benchmark data
**never** lives inside the repository.

## Usage

```bash
uv run voz bench \
  --model-dir <model-directory> \
  --source Systran/faster-whisper-large-v3 \
  --revision edaa852ec7e145841d8ffdb056a99866b5f0a478 \
  --device cuda            # cuda | cpu
  --dataset <name|path>    # see "Personal dataset"
  [--compute-type float16|int8_float16|int8]   # default float16 (cuda) / int8 (cpu)
  [--engine faster-whisper|whisper-cpp] [--language es] [--json]
```

- `--model-dir` is required and used as given: `voz bench` neither downloads nor
  searches for models. `--source` and `--revision` must match an entry of V's
  pinned catalog (so the provenance of the result is never invented). With
  `--engine whisper-cpp`, `--source` is the model id (`large-v3-turbo-q5_0`)
  because they all share one repo; it requires `VOZ_WHISPER_CPP_BIN` or
  `whisper-cli` on the `PATH`, and it is only measured on `cpu`.
- Output is text (a per-clip table plus totals) or `--json` (`schema_version: 1`,
  no host paths). Errors: `benchmark_*` with exit code 2; engine failures, exit
  code 1.

### What is measured

| Metric | How |
| --- | --- |
| Load time | first transcription of 1 s of silence (forces the model's lazy load; includes ~1 s of inference). With whisper.cpp the model is reloaded on every call, so this is the per-call startup cost. |
| Time and RTF | `perf_counter` around each clip; RTF = compute seconds / audio seconds (< 1 is faster than real time). Totals sum the clips. |
| RAM | peak RSS (`ru_maxrss`) of the process; with whisper.cpp, of the largest child process. It is the peak of the **whole process** (interpreter and libraries included); `ram_delta` is the final peak minus the peak before loading the model. |
| VRAM | peak **sampled** every 0.2 s with `nvidia-smi` in a thread (a lower bound: it can miss peaks shorter than the interval). The prior baseline and the delta are reported; `n/d` (the literal the CLI prints for "not available") without a GPU or on `cpu`. |
| WER / CER | `application/evaluation.py`; see below. Corpus rate = total edits / total reference length (not the average of per-clip rates). |

### WER / CER (S13.10)

Pure functions using the standard library. Normalization of both texts: NFKC,
`casefold`, every punctuation or symbol character (`P*`, `S*`) becomes a space
(apostrophes and hyphens separate words), spaces collapsed. **Accents and digits
are preserved**: "está" ≠ "esta" and "3" ≠ "tres" (numbers are not converted, so
as not to hide real errors). The distance is Levenshtein (substitution,
insertion and deletion cost 1) over words (WER) or characters (CER, counting
single spaces). WER can exceed 100 %. Empty reference: 0 if the hypothesis is
also empty, no rate otherwise.

## Personal dataset outside Git (S13.09)

`--dataset <name>` reads `$XDG_DATA_HOME/voz/benchmarks/<name>/` (by default
`~/.local/share/voz/benchmarks/<name>/`); a value containing `/` or starting with
`.` is taken as a path. If the directory (or the data directory) falls **inside
the repository checkout**, the command refuses (`benchmark_dataset_inside_checkout`),
covered by tests. Audio and references are private data: do not copy them into the
repo.

`manifest.json`:

```json
{
  "language": "es",
  "items": [
    {"audio": "reunion1.wav", "reference": "exact text spoken in the audio"},
    {"audio": "reunion2.wav", "reference_file": "reunion2.txt"},
    {"audio": "sin_referencia.wav"}
  ]
}
```

Paths are relative to the dataset and cannot leave it. A clip without a reference
only contributes time/memory. `language` is optional (`--language` overrides it;
with neither, the engine detects the language).

## Measured results (S13.07)

> **Read this before using the numbers.** The audio is **synthetic** (`espeak-ng`,
> Spanish voice, no noise, a single speaker, simple vocabulary). It measures
> speed, memory and consistency between models; it **does not represent real
> classes** (several speakers, echo, noise, accents). The WER here is optimistic
> and must not be quoted as real accuracy. One measurement per configuration (no
> repetitions), with other development processes possibly running on the machine:
> CPU times are noisy.

- **Date:** 2026-09-30. **Repo base commit:** `dc842ae` (tree with uncommitted
  changes from other slices of wave 5c).
- **Hardware:** Intel Core i7-13650HX (20 threads), NVIDIA GeForce RTX 4060 Laptop
  8 GB (8188 MiB), Linux 7.2.7 (Bazzite/Fedora 44), Python 3.14.7.
- **Versions:** faster-whisper 1.2.1, CTranslate2 4.8.2, espeak-ng 1.52.0,
  whisper.cpp v1.9.4 (CPU-only build, `-DGGML_NATIVE=ON`, GCC 16.2.1).
- **Models** (pinned revisions of V's catalog):
  `mobiuslabsgmbh/faster-whisper-large-v3-turbo@0a363e91…`,
  `Systran/faster-whisper-large-v3@edaa852e…`,
  `ggerganov/whisper.cpp@5359861c…` `ggml-large-v3-turbo-q5_0.bin`
  (SHA-256 verified `394221709cd5…ffa7e2`).
- **Dataset:** language `es`, 6 clips of 34–39 s (217 s in total, 96–105 words and
  540–614 reference characters each, hand-written texts) and 1 long clip of 434.6
  s (7.2 min) that **concatenates the same 6 clips twice** (the reference text is
  repeated). Generated in a temporary directory outside the repo and deleted
  afterwards; it is not versioned. Reproducible: same text + `espeak-ng -v es -s
  160` + `ffmpeg -ar 16000 -ac 1`.
- **Command:** the one in "Usage" with `--dataset <temporary dir>`; results with
  `--json`.

### Short clips (6 × ~36 s)

| Configuration | Load | RTF | WER | CER | Peak RAM | Peak VRAM (base 80) |
| --- | --- | --- | --- | --- | --- | --- |
| faster-whisper turbo, CUDA float16 | 2.6 s | 0.025 | 1.66 % | 0.81 % | 2163 MiB | 2344 MiB |
| faster-whisper large-v3, CUDA float16 | 2.6 s | 0.073 | 1.99 % | 0.81 % | 3576 MiB | 5512 MiB |
| faster-whisper turbo, CPU int8 | 20.8 s | 0.242 | 1.83 % | 0.84 % | 2092 MiB | n/d |
| whisper.cpp turbo q5_0, CPU | 12.2 s | 0.804 | 1.83 % | 0.84 % | 958 MiB | n/d |

### Long clip (434.6 s)

| Configuration | Time | RTF | WER | CER |
| --- | --- | --- | --- | --- |
| faster-whisper turbo, CUDA float16 | 10.1 s | 0.023 | 1.66 % | 0.92 % |
| faster-whisper large-v3, CUDA float16 | 52.7 s | 0.121 | **8.14 %** | 6.31 % |
| faster-whisper turbo, CPU int8 | 89.4 s | 0.206 | 1.58 % | 0.88 % |
| whisper.cpp turbo q5_0, CPU | 319.4 s | 0.735 | 2.33 % | 1.50 % |

### What can and cannot be concluded

- On this machine turbo on GPU is ~3 times faster than large-v3 on short clips
  and uses ~3.2 GB less VRAM (large-v3 uses 5.5 of 8 GB: it fits, but with little
  margin for other GPU loads). With clean synthetic audio both score almost the
  same on short clips.
- large-v3 got much worse on the long clip (8.14 %), **not on the short ones**.
  The cause was not investigated; one hypothesis is that the repeated text of the
  long clip (the same content twice) favors omissions or repetitions, an artifact
  of this dataset. The transcript would have to be reviewed and the test repeated
  with real audio before drawing a conclusion about large-v3.
- CPU with faster-whisper int8 (RTF 0.2) is usable; whisper.cpp q5_0 with the
  adapter's flags is ~3.3 times slower (RTF 0.8) but uses less than half the RAM.
  Both use 4 threads by default (`whisper-cli -t` = 4; CTranslate2 with
  `cpu_threads=0`); threads were not tuned.
- Each run is a single pass with no repetitions or measured variance.

## Real whisper.cpp: the `-ojf` format (S9.10)

Build verified on this machine (CPU only): `uvx cmake`, GCC 16.2.1, `cmake -B
build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON` and `cmake --build build
--target whisper-cli` on tag **v1.9.4**; the binary accepts every flag that
`probe_whisper_cpp` requires. The real output of `--output-json-full` (keys
`systeminfo`, `model`, `params`, `result.language`,
`transcription[].offsets/text/tokens[].{text,offsets,id,p,t_dtw}`) matches what
the adapter reads; an excerpt was saved in
`tests/fixtures/whisper_cpp/real_ojf_v1.9.4.json` and
`tests/unit/infrastructure/asr/test_whisper_cpp_real_format.py` checks that
`WhisperCppProvider` maps it to segments and words. No format discrepancies.
Documentation discrepancies found at the time:

- `whisper-cpp.md` said `git checkout 5359861c…  # same revision as the catalog`,
  but that revision belongs to the **models** repo on Hugging Face
  (`ggerganov/whisper.cpp`), not a commit of the code repo (it does not exist
  there). To build, a tag must be used, for example `v1.9.4`. (Already corrected
  in [whisper-cpp.md](whisper-cpp.md).)
- Build with CUDA/Vulkan: not tested here (CPU only).

## Known limitations

- A single GPU (`nvidia-smi` first GPU); without NVIDIA, VRAM is `n/d`.
- The RAM peak is for the whole process and does not separate the model from the
  libraries.
- The VRAM peak is sampled: a lower bound.
- Load includes 1 s of inference (see the metrics table).

## Checkpoint frequency: synthetic CPU comparison (2026-10-16)

This experiment compares 10, 15 and 30 minute audio chunks through
`RecoverableTranscription` and its real SQLite checkpoint adapter. The
[checkpoint harness](../scripts/benchmark-checkpoints.py) plans without loading
a model by default; `--run` executes each policy in a separate process with
isolated HOME/XDG directories. The production default remains **30 minutes**.

### Setup and scope

- Measurement started at 2026-10-16 17:07:42 UTC. Script SHA-256:
  `d7ec3647b61dd53618a22d4627a79c819135fd955df74676828c2c3a496c0d3e`.
- Hardware: Intel Core i7-13650HX, 20 logical CPUs. Linux 7.2.9, Python 3.12.14,
  faster-whisper 1.2.1, CTranslate2 4.8.2, eSpeak NG 1.52.0 and FFmpeg 8.1.3.
  Execution was CPU/int8 with the installed runtime's default thread count.
- Model: `Systran/faster-whisper-base`, pinned revision
  `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`. Required files totaled
  147,882,941 bytes and matched the catalog sizes. The weight SHA-256 matched
  `d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9`.
  The existing local HF snapshot was read directly; no model was downloaded.
- Corpus: **synthetic, sparse, single-speaker Spanish**, generated with
  `espeak-ng -v es -s 160`, then normalized to mono PCM16 at 16 kHz. It contains
  1,860 seconds of audio, including 322.114 seconds of speech in 62 utterances,
  744 reference words and 5,066 normalized reference characters. Sentence
  templates repeat with different nouns and colors; most of the timeline is
  silence. This is not representative of recorded classes or conversations.
- The three generated WAV files were byte-identical, SHA-256
  `7611ed2d97cbe5dd67d82df41fad8e1b5f0a0610f50e2830826838d8190d31c8`.
- Storage was persistent `btrfs`, with SQLite WAL and synchronous FULL.
  Timings include checkpoint commits on this filesystem; successful readback
  does not establish durability after power loss.
- Serial order: 30 → 15 → 10 minutes, **n=1 per policy**, with no measured
  variance and no control over other development processes. Each process had
  a 300 second limit covering preparation, model verification, warmup,
  transcription and scoring. All three completed with exit code 0 and were
  reaped; no trial reached its timeout. Separate automated tests exercise
  timeout, interruption and descendant cleanup.

Pipeline wall time starts after database seeding and warmup and ends when
recoverable transcription returns. It includes PCM extraction, inference,
progress persistence, atomic checkpoints and orchestration. Reference scoring
is outside that interval. Warmup used one second of silence and took
0.742 / 0.620 / 0.708 seconds for the 30 / 15 / 10 minute policies. Whole
supervised trial elapsed times were 46.179 / 41.275 / 44.581 seconds.

### Measured time and checkpoint overhead

The overlap was five seconds on each side of every internal cut. All confirmed
checkpoints were read back from SQLite before reporting their count.

| Chunk duration | Checkpoints | Processed audio | Pipeline wall | Inference | PCM extraction | Checkpoint commits | Other overhead | Wall delta vs 30 min |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 min | 4 | 1,890 s | 33.762 s | 33.714 s | 28.048 ms | 13.127 ms | 6.280 ms | -5.64 % |
| 15 min | 3 | 1,880 s | 31.173 s | 31.122 s | 35.725 ms | 9.214 ms | 5.527 ms | -12.88 % |
| 30 min | 2 | 1,870 s | 35.781 s | 35.732 s | 35.471 ms | 7.502 ms | 6.171 ms | baseline |

The longest observed wall interval from transcription start or the previous
successful checkpoint through the next successful checkpoint was 12.136,
15.228 and 34.603 seconds for 10, 15 and 30 minute chunks, respectively.
These are measured compute intervals on this corpus and model, not audio
durations or guarantees for other workloads. The wall deltas are single-run
observations; the faster shorter-chunk runs do not establish a repeatable speedup.

### Measured global and boundary quality

| Chunk duration | Global WER | Word edits / reference words | Global CER |
| --- | --- | --- | --- |
| 10 min | 31.32 % | 233 / 744 | 11.59 % |
| 15 min | 34.27 % | 255 / 744 | 13.48 % |
| 30 min | 52.02 % | 387 / 744 | 21.08 % |

Boundary windows are common to every policy: ±15 seconds around 10, 15, 20
and 30 minutes, the union of their internal cuts. A complete synthesized
utterance crosses each window's center. The reference consists of full
utterances contained in that window; the hypothesis uses the midpoints of
the retained ASR words after the production ownership/clamping rules. These
scores combine recognition and ownership effects; they do not isolate the
cause of an error. Missing word timestamps are reported as unavailable.

Each cell below is **WER / CER**. An asterisk marks an actual cut for that
policy; unmarked cells measure the same window without a cut at its center.

| Window center | 10 min chunks | 15 min chunks | 30 min chunks |
| --- | --- | --- | --- |
| 10 min | 66.67 % / 47.44 % * | 50.00 % / 26.92 % | 50.00 % / 26.92 % |
| 15 min | 16.67 % / 3.70 % | 75.00 % / 69.14 % * | 58.33 % / 39.51 % |
| 20 min | 50.00 % / 44.30 % * | 16.67 % / 7.59 % | 50.00 % / 24.05 % |
| 30 min | 58.33 % / 43.21 % * | 41.67 % / 39.51 % * | 75.00 % / 64.20 % * |

The boundary comparison is mixed, and absolute error rates are high on this
sparse, repetitive corpus. A single synthetic run cannot establish real-world
accuracy, variance or an optimal checkpoint frequency. No default change is
supported by this experiment alone.

### Reproduce with an existing pinned snapshot

Run from the repository root, supplying the existing external snapshot in
`MODEL_SNAPSHOT`. The output directory must not already exist. The script
rejects output inside the checkout and verifies the
catalog weight hash before inference. On POSIX it kills its process group
on exit, including descendants, and uses a bounded wait to reap the child.

```bash
run_dir=$(mktemp -d)
env HOME="$run_dir" \
  XDG_DATA_HOME="$run_dir/data" XDG_CONFIG_HOME="$run_dir/config" \
  XDG_CACHE_HOME="$run_dir/cache" XDG_STATE_HOME="$run_dir/state" \
  .venv/bin/python scripts/benchmark-checkpoints.py \
  --run --model-id base --model-dir "$MODEL_SNAPSHOT" \
  --output-dir "$run_dir/results" --timeout-seconds 300
```

`report.json` contains trial status, measured timing, global WER/CER and the
window references/hypotheses. Each trial also retains its synthetic WAV,
reference spans, SQLite database and logs outside Git. A timeout or failure
has no fabricated transcription metrics. Planning without inference:
`.venv/bin/python scripts/benchmark-checkpoints.py`.
