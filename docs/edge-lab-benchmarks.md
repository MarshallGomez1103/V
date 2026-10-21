# Edge Lab benchmark definitions: STT and TTS

These definitions use the version 1 local experiment contract described in
[Edge Lab](edge-lab.md), with the resource boundaries of
[ADR-0011](adr/0011-edge-lab.md). Models and runtimes must already be installed.
Definitions, datasets and input text belong outside the source checkout.
Running an experiment does not download models or install dependencies.

## STT: retain the existing bench contract

Save this definition in a private experiment directory, with the referenced
model and dataset already present relative to that directory:

```json
{
  "schema_version": 1,
  "workload": "stt",
  "profile": {
    "device": "cpu",
    "cpu_mask": null,
    "address_space_bytes": 2147483648,
    "systemd": false
  },
  "model": {
    "engine": "faster-whisper",
    "model_id": "tiny",
    "directory": "../models/faster-whisper-tiny"
  },
  "input": {
    "path": "../datasets/speech",
    "language": "es"
  },
  "timeout_seconds": 120
}
```

The dataset uses the existing [bench manifest](benchmarks.md). STT preserves
its scoring and timing: RTF is wall seconds / input audio seconds; WER/CER use
corpus edit totals and the documented normalization. No reference means no
accuracy observation. Warm-up includes one second of silent inference; it is
not pure model-load time. The bench schema remains version 1.

Faster Whisper uses CPU int8. For `whisper-cpp`, select a model ID from its
catalog and its installed local directory; quantization follows that file,
not the bench `compute_type` label. Catalog identity does not prove that a
supplied STT directory matches its pinned revision: files are not rehashed.

## TTS: completed chunks and render throughput

An installed catalog voice and a private UTF-8 text file define a TTS run:

```json
{
  "schema_version": 1,
  "workload": "tts",
  "profile": {
    "device": "cpu",
    "cpu_mask": null,
    "address_space_bytes": 2147483648,
    "systemd": false
  },
  "model": {
    "engine": "sherpa-onnx-tts",
    "model_id": "kitten-nano-en-v0_8-int8"
  },
  "input": {
    "path": "../inputs/speech.txt",
    "voice_id": "0",
    "speed": 1.0
  },
  "timeout_seconds": 120
}
```

The model is resolved through V's existing TTS store; this definition cannot
override its directory or load arbitrary engine code. Input remains bounded
to 65,536 bytes and 20,000 characters. Voice, speed, native sample rate and
chunking follow the existing synthesis provider. Each chunk is rendered once;
there is no additional warm-up or automatic repetition.

Run the saved definition with `v lab run` or `voz lab run`. Relative paths are
resolved against the definition file; a leading `~` expands first. The limits
and setup deadlines remain those of the Edge Lab supervisor. CPU is the
implemented device; requesting CUDA or systemd reports unavailable capability.

### Clock boundaries

The render clock starts immediately before the first `synthesize` call, after
model metadata, input reading, provider construction and chunk planning.
`first_audio_seconds` is captured when the first call returns valid PCM.
The provider currently returns a complete chunk after its native child has
finished and been cleaned up. This metric therefore measures **the first
completed chunk available to the caller**, including that child's model load
and teardown. It does not measure a native callback, the first sample arriving
on a pipe, playback start or sample streaming.

`wall_seconds` ends after all chunks return and the provider is closed. It
includes per-chunk model loading, rendering, loop overhead and teardown,
including final provider close. It excludes input preparation and supervisor
startup, and is not isolated CPU execution time. The overall experiment
deadline still covers setup, loading and inference; cleanup waits are bounded
separately by the supervisor.

### Measurements

All fields below are observations under `measured`. Existing TTS fields and
model/voice/thread observations are retained; the envelope and `estimated`
remain unchanged. `estimated` is empty.

| Field | Unit and interpretation |
| --- | --- |
| `first_audio_seconds` | Seconds to the first completed chunk returned, with the clock boundaries above. Later chunks do not overwrite it. |
| `wall_seconds` | Render wall seconds through provider close. |
| `output_audio_seconds` | Total mono frames / native sample rate, accounting for the PCM sample width. |
| `throughput_audio_seconds_per_second` | `output_audio_seconds / wall_seconds`; a higher value means more rendered audio per wall second. |
| `frames`, `sample_rate`, `chunks` | Rendered mono frame count, native samples per second and completed text chunk count. |
| `input_characters` | Character count of the private input text; the text itself is not included. |
| `memory.worker_peak_rss_mib` | Worker lifetime peak RSS, including interpreter, metadata and collected PCM. |
| `memory.largest_child_peak_rss_mib` | Largest completed child RSS high-water mark as reported by `RUSAGE_CHILDREN`. It is not summed child memory. |

The memory fields retain their separate scopes. They must not be added or
reported as the simultaneous peak RSS of the process tree. They also do not
measure virtual address space, GPU memory or cgroup-accounted memory. Linux
RSS accounting uses KiB and is converted to MiB; macOS accounting uses bytes.
Other platforms, missing accounting, failed reads and absent or invalid peaks
produce `null`, with a stable reason under `memory.unavailable_reasons`.
Unavailable memory is not replaced by zero or an estimate.

Rendered duration counts PCM from the chunks only. The command does not add
silence between chunks, assemble a WAV, save generated audio or claim streaming.
Both int16 and float32 PCM use frames rather than raw byte count for duration.
Changing sample rates across chunks, empty PCM, nonfinite times, a nonpositive
wall duration or inconsistent first-chunk timing fail the benchmark.

## Failure and interpretation limits

A model/runtime check or readiness record alone cannot produce a completed
measurement. Rendering failure, cancellation or deadline expiration follows
the existing failed/interrupted envelope; no successful metrics are returned.
The provider is closed on setup or render failure as well as on completion.
The supervisor continues to own process-tree termination and resource limits.

Reports contain neither source paths nor input text. A single pass has no
measured variance, and synthetic input does not establish accuracy or perceived
voice quality on real material. Constrained PC measurements do not establish
ARM equivalence or untested operating-system/device support. Deterministic
tests with fake clocks, providers and RSS readers validate the metric contract;
they are not real-model hardware benchmark results.
